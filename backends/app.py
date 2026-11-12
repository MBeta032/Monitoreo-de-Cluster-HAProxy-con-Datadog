import os
import time
import json
import logging
import sys
from datetime import timedelta
import psycopg
from flask import Flask, abort, g, jsonify, redirect, render_template, request, Response, session, url_for
from prometheus_client import (
    CONTENT_TYPE_LATEST,
    CollectorRegistry,
    Counter,
    Histogram,
    generate_latest,
    multiprocess,
)

import auth
import db

app = Flask(__name__)

INSTANCE_NAME = os.getenv("INSTANCE_NAME", "backend-local")

# Sesión con la cookie firmada de Flask: la sesión no vive en la memoria de un backend.
# SECRET_KEY firma la cookie y debe ser la MISMA en los 3 backends; así cualquiera de ellos
# reconoce la sesión que creó otro (README, sección 6).
secret_key = os.getenv("SECRET_KEY")
if not secret_key:
    raise RuntimeError("Falta la variable SECRET_KEY (ver .env.example)")
app.config["SECRET_KEY"] = secret_key
app.config["SESSION_COOKIE_HTTPONLY"] = True
app.config["SESSION_COOKIE_SAMESITE"] = "Lax"
# False porque el laboratorio va por HTTP. En producción, con HTTPS, va en True.
app.config["SESSION_COOKIE_SECURE"] = False
app.config["PERMANENT_SESSION_LIFETIME"] = timedelta(hours=2)

# Configuración de log estructurado en JSON hacia stdout
class JsonFormatter(logging.Formatter):
    def format(self, record):
        log_record = {
            "timestamp": int(time.time() * 1000),
            "level": record.levelname,
            "message": record.getMessage(),
            "instance": os.getenv("INSTANCE_NAME", "backend-local")
        }
        if hasattr(record, "request_info"):
            log_record.update(record.request_info)
        return json.dumps(log_record)

handler = logging.StreamHandler(sys.stdout)
handler.setFormatter(JsonFormatter())
logger = logging.getLogger("backend_logger")
logger.setLevel(logging.INFO)
logger.addHandler(handler)
logger.propagate = False

# Métricas estándar de Prometheus (OpenMetrics)
HTTP_REQUESTS_TOTAL = Counter(
    'http_requests_total',
    'Total de peticiones HTTP atendidas',
    ['method', 'handler', 'status']
)

HTTP_REQUEST_DURATION_SECONDS = Histogram(
    'http_request_duration_seconds',
    'Duracion de peticiones HTTP en segundos',
    ['method', 'handler']
)

# Rutas operativas excluidas de la telemetria de trafico
EXCLUDED_PATHS = {'/health', '/metrics'}

@app.before_request
def start_timer():
    request._start_time = time.time()

@app.after_request
def record_metrics_and_log(response):
    path = request.path
    method = request.method
    status_code = str(response.status_code)
    
    # Excluir /health y /metrics de contadores, latencias y logs
    if path not in EXCLUDED_PATHS:
        duration = time.time() - getattr(request, '_start_time', time.time())

        # El label handler usa la ruta plantilla de Flask (por ejemplo /api/events/<int:event_id>)
        # y no la ruta escrita por el usuario, para no crear una serie por cada URL distinta.
        # Si ninguna ruta coincide (404 o 405), se usa un valor fijo.
        if request.url_rule is not None:
            handler_label = request.url_rule.rule
        else:
            handler_label = "unmatched"

        HTTP_REQUESTS_TOTAL.labels(method=method, handler=handler_label, status=status_code).inc()
        HTTP_REQUEST_DURATION_SECONDS.labels(method=method, handler=handler_label).observe(duration)
        
        # Log de aplicacion estructurado en JSON
        log_payload = {
            "request_info": {
                "method": method,
                "path": path,
                "status_code": response.status_code,
                "duration_ms": round(duration * 1000, 2),
                "client_ip": request.remote_addr
            }
        }
        message = f"Peticion procesada {method} {path} - {status_code}"

        # Nivel del log segun el resultado: 5xx es ERROR, 4xx es WARNING y el resto INFO
        if response.status_code >= 500:
            logger.error(message, extra=log_payload)
        elif response.status_code >= 400:
            logger.warning(message, extra=log_payload)
        else:
            logger.info(message, extra=log_payload)

    return response

# --- Boletería: páginas web ---

@app.context_processor
def inject_common_values():
    # Todas las plantillas reciben: el nombre de la instancia (pie de página), el usuario de la
    # sesión (encabezado) y la función csrf_token() para los formularios POST.
    return {
        "instance_name": INSTANCE_NAME,
        "current_user": auth.get_current_user(),
        "csrf_token": auth.get_csrf_token,
    }

def group_seats(seats):
    # Agrupa las sillas por sección y por fila, en el mismo orden en que llegan de la base.
    # Resultado: {"Preferencial": {"A": [silla, silla, ...], "B": [...]}, "General": {...}}
    sections = {}
    for seat in seats:
        rows = sections.setdefault(seat["section"], {})
        rows.setdefault(seat["seat_row"], []).append(seat)
    return sections

@app.route('/')
def index():
    events = db.list_events()
    return render_template("index.html", events=events)

@app.route('/events/<int:event_id>')
def event_page(event_id):
    event = db.get_event(event_id)
    if event is None:
        abort(404)
    seats = db.list_seats(event_id)
    return render_template("event.html", event=event, sections=group_seats(seats))

# --- Cuentas: iniciar sesión, crear cuenta y cerrar sesión ---

def get_next_url():
    # Página a la que se vuelve después de iniciar sesión. Solo se aceptan rutas internas.
    next_url = request.values.get("next", "")
    if auth.is_safe_next(next_url):
        return next_url
    return url_for("index")

def validate_registration(name, email, password):
    # Devuelve el mensaje de error, o None si los datos de la cuenta nueva están bien
    if name == "":
        return "Escribe tu nombre."
    if len(name) > 100:
        return "El nombre no puede tener más de 100 caracteres."
    if not is_valid_email(email):
        return "El correo no es válido."
    if len(password) < auth.MIN_PASSWORD_LENGTH:
        return f"La contraseña debe tener al menos {auth.MIN_PASSWORD_LENGTH} caracteres."
    return None

@app.route('/login', methods=['GET', 'POST'])
def login():
    next_url = get_next_url()
    if request.method == 'GET':
        return render_template("auth.html", mode="login", next_url=next_url)

    if not auth.csrf_token_is_valid(request.form.get("csrf_token")):
        abort(403)

    email = request.form.get("email", "").strip().lower()
    password = request.form.get("password", "")
    user = db.get_user_by_email(email)
    if user is None or not auth.password_matches(user["password_hash"], password):
        return render_template(
            "auth.html", mode="login", next_url=next_url, email=email,
            error_message="Correo o contraseña incorrectos.",
        ), 401

    auth.start_session(user["id"])
    return redirect(next_url)

@app.route('/register', methods=['GET', 'POST'])
def register():
    next_url = get_next_url()
    if request.method == 'GET':
        return render_template("auth.html", mode="register", next_url=next_url)

    if not auth.csrf_token_is_valid(request.form.get("csrf_token")):
        abort(403)

    name = request.form.get("name", "").strip()
    email = request.form.get("email", "").strip().lower()
    password = request.form.get("password", "")
    error_message = validate_registration(name, email, password)
    if error_message is not None:
        return render_template(
            "auth.html", mode="register", next_url=next_url, name=name, email=email,
            error_message=error_message,
        ), 400

    user_id = db.create_user(name, email, auth.hash_password(password))
    if user_id is None:
        return render_template(
            "auth.html", mode="register", next_url=next_url, name=name, email=email,
            error_message="Ya existe una cuenta con ese correo. Inicia sesión.",
        ), 409

    auth.start_session(user_id)
    return redirect(next_url)

@app.route('/logout', methods=['POST'])
def logout():
    if not auth.csrf_token_is_valid(request.form.get("csrf_token")):
        abort(403)
    session.clear()
    return redirect(url_for("index"))

@app.route('/health')
def health():
    return jsonify({"status": "UP"}), 200

@app.route('/error')
def trigger_error():
    return jsonify({
        "error": "Internal Server Error",
        "message": "Error forzado para pruebas de monitoreo"
    }), 500

@app.route('/metrics')
def metrics():
    # Modo multiproceso: suma las métricas de todos los workers de Gunicorn,
    # leyendo los archivos de PROMETHEUS_MULTIPROC_DIR (documentación de prometheus-client)
    registry = CollectorRegistry()
    multiprocess.MultiProcessCollector(registry)
    return Response(generate_latest(registry), mimetype=CONTENT_TYPE_LATEST)

# --- Boletería: API JSON ---

def event_to_json(event):
    return {
        "id": event["id"],
        "name": event["name"],
        "venue": event["venue"],
        "starts_at": event["starts_at"].isoformat(),
        "available_seats": event["available_seats"],
        "total_seats": event["total_seats"],
    }

def is_valid_email(email):
    # Validación simple: sin espacios, un solo @, algo antes y un dominio con punto después
    if len(email) > 254 or " " in email:
        return False
    if email.count("@") != 1:
        return False
    local_part, domain = email.split("@")
    if local_part == "":
        return False
    if "." not in domain or domain.startswith(".") or domain.endswith("."):
        return False
    return True

def validate_buyer(data):
    # Devuelve el mensaje de error, o None si los datos del comprador están bien
    if not isinstance(data, dict):
        return "El cuerpo debe ser un JSON con buyer_name y buyer_email"

    buyer_name = data.get("buyer_name")
    if not isinstance(buyer_name, str) or buyer_name.strip() == "":
        return "Falta el nombre del comprador (buyer_name)"
    if len(buyer_name.strip()) > 100:
        return "El nombre no puede tener más de 100 caracteres"

    buyer_email = data.get("buyer_email")
    if not isinstance(buyer_email, str) or buyer_email.strip() == "":
        return "Falta el correo del comprador (buyer_email)"
    if not is_valid_email(buyer_email.strip()):
        return "El correo no es válido"

    return None

@app.route('/api/info')
def api_info():
    return jsonify({"instance": INSTANCE_NAME}), 200

@app.route('/api/login', methods=['POST'])
def api_login():
    # No lleva token CSRF: el cuerpo es JSON y un formulario de otro sitio no puede enviar JSON.
    # Responde el token que el cliente debe enviar en X-CSRF-Token en los demás POST de la API.
    data = request.get_json(silent=True)
    if not isinstance(data, dict) or not isinstance(data.get("email"), str) or not isinstance(data.get("password"), str):
        return jsonify({"error": "Bad Request", "message": "Envía un JSON con email y password"}), 400

    email = data["email"].strip().lower()
    user = db.get_user_by_email(email)
    if user is None or not auth.password_matches(user["password_hash"], data["password"]):
        return jsonify({"error": "Unauthorized", "message": "Correo o contraseña incorrectos"}), 401

    auth.start_session(user["id"])
    return jsonify({
        "user": {"id": user["id"], "name": user["name"], "email": user["email"]},
        "csrf_token": session["csrf_token"],
    }), 200

@app.route('/api/logout', methods=['POST'])
def api_logout():
    if not auth.csrf_token_is_valid(request.headers.get("X-CSRF-Token")):
        return jsonify({"error": "Forbidden", "message": "Token CSRF inválido o ausente"}), 403
    session.clear()
    return jsonify({"message": "Sesión cerrada"}), 200

@app.route('/api/events')
def api_list_events():
    events = db.list_events()
    return jsonify([event_to_json(event) for event in events]), 200

@app.route('/api/events/<int:event_id>')
def api_get_event(event_id):
    event = db.get_event(event_id)
    if event is None:
        return jsonify({"error": "Not Found", "message": "El evento no existe"}), 404
    return jsonify(event_to_json(event)), 200

@app.route('/api/events/<int:event_id>/seats')
def api_list_seats(event_id):
    event = db.get_event(event_id)
    if event is None:
        return jsonify({"error": "Not Found", "message": "El evento no existe"}), 404
    seats = db.list_seats(event_id)
    return jsonify(seats), 200

@app.route('/api/events/<int:event_id>/seats/<int:seat_id>/purchase', methods=['POST'])
def api_purchase_seat(event_id, seat_id):
    data = request.get_json(silent=True)
    error_message = validate_buyer(data)
    if error_message is not None:
        return jsonify({"error": "Bad Request", "message": error_message}), 400

    buyer_name = data["buyer_name"].strip()
    buyer_email = data["buyer_email"].strip()
    seat = db.purchase_seat(event_id, seat_id, buyer_name, buyer_email)
    if seat is not None:
        seat["sold_at"] = seat["sold_at"].isoformat()
        return jsonify(seat), 201

    # No se vendió: o la silla no existe en este evento, o alguien la compró antes
    if db.seat_exists(event_id, seat_id):
        return jsonify({"error": "Conflict", "message": "Esa silla ya fue vendida"}), 409
    return jsonify({"error": "Not Found", "message": "La silla no existe en este evento"}), 404

@app.errorhandler(psycopg.OperationalError)
def database_unavailable(error):
    # La base no responde: error de conexión, o se acabó la espera por una conexión del pool
    # (PoolTimeout también es un OperationalError). Esta respuesta pasa por after_request,
    # así que se cuenta en las métricas y deja una línea de log con level ERROR.
    # La API responde JSON; las páginas web responden una página HTML sencilla.
    if request.path.startswith("/api/"):
        return jsonify({
            "error": "Service Unavailable",
            "message": "La base de datos no responde. Intenta de nuevo en unos minutos."
        }), 503
    # El encabezado no consulta al usuario: la base está caída
    g.user = None
    return render_template("503.html"), 503

if __name__ == '__main__':
    # Solo para pruebas manuales sin Gunicorn: abre el pool aquí
    db.pool.open()
    port = int(os.getenv("PORT", 5000))
    app.run(host='0.0.0.0', port=port)
