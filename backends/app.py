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

def reservation_code(reservation_id):
    # Código que ve el usuario: "TS-" más el id con 6 dígitos (TS-000482)
    return f"TS-{reservation_id:06d}"

# Las plantillas lo usan como filtro: {{ reservation.id | reservation_code }}
app.add_template_filter(reservation_code)

def group_seats_by_row(seats):
    # Agrupa las sillas de una zona por fila, en el mismo orden en que llegan de la base.
    # Resultado: {"A": [silla, silla, ...], "B": [...]}
    rows = {}
    for seat in seats:
        rows.setdefault(seat["seat_row"], []).append(seat)
    return rows

@app.route('/')
def index():
    events = db.list_events()
    return render_template("index.html", events=events)

@app.route('/events/<int:event_id>')
def event_page(event_id):
    # Nivel 1: plano de zonas. Nivel 2 (?section=<zona>): las sillas de esa zona.
    # Si el evento tiene una sola zona, se muestran sus sillas directamente.
    event = db.get_event(event_id)
    if event is None:
        abort(404)
    sections = db.list_sections(event_id)

    selected_name = request.args.get("section")
    if selected_name is None and len(sections) == 1:
        selected_name = sections[0]["section"]
    if selected_name is None:
        return render_template("venue_map.html", event=event, sections=sections)

    selected_section = None
    for section in sections:
        if section["section"] == selected_name:
            selected_section = section
    if selected_section is None:
        abort(404)

    seats = db.list_section_seats(event_id, selected_name)
    return render_template(
        "event.html",
        event=event,
        section=selected_section,
        rows=group_seats_by_row(seats),
        has_many_sections=len(sections) > 1,
    )

# --- Reserva: confirmar, listo y mis reservas ---

@app.route('/events/<int:event_id>/confirm')
def confirm_page(event_id):
    seat_id = request.args.get("seat", type=int)
    if seat_id is None:
        abort(404)
    # Sin sesión: primero iniciar sesión y volver aquí. Se pasa también la silla
    # para que la página de inicio de sesión muestre qué se está reservando.
    if auth.get_current_user() is None:
        return redirect(url_for("login", next=request.full_path, seat=seat_id))

    seat = db.get_seat(event_id, seat_id)
    if seat is None:
        abort(404)
    seat_taken = seat["status"] != "available"
    return render_template("confirm.html", seat=seat, seat_taken=seat_taken)

@app.route('/events/<int:event_id>/confirm', methods=['POST'])
def confirm_reservation(event_id):
    seat_id = request.form.get("seat_id", type=int)
    # La sesión se revisa ANTES que el token CSRF: si la sesión venció, el token tampoco existe.
    # Sin sesión se vuelve a la página Confirmar con la silla (como en el GET), no al POST.
    user = auth.get_current_user()
    if user is None:
        confirm_url = url_for("confirm_page", event_id=event_id, seat=seat_id)
        return redirect(url_for("login", next=confirm_url, seat=seat_id))

    if not auth.csrf_token_is_valid(request.form.get("csrf_token")):
        abort(403)
    if seat_id is None:
        abort(404)

    reservation = db.reserve_seat(event_id, seat_id, user["id"])
    if reservation is not None:
        # Patrón POST/Redirect/GET: recargar la página Listo no repite la reserva
        return redirect(url_for("reservation_page", reservation_id=reservation["id"]), code=303)

    # No se pudo reservar: la silla no existe en este evento, o alguien la reservó antes
    seat = db.get_seat(event_id, seat_id)
    if seat is None:
        abort(404)
    return render_template("confirm.html", seat=seat, seat_taken=True), 409

@app.route('/reservations')
@auth.login_required
def reservations_page():
    reservations = db.list_user_reservations(auth.get_current_user()["id"])
    return render_template("reservations.html", reservations=reservations)

@app.route('/reservations/<int:reservation_id>')
@auth.login_required
def reservation_page(reservation_id):
    # Pantalla "Listo". Solo la ve el dueño de la reserva: la de otro usuario da 404.
    reservation = db.get_reservation(reservation_id, auth.get_current_user()["id"])
    if reservation is None:
        abort(404)
    return render_template("reservation_done.html", reservation=reservation)

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
        "category": event["category"],
        "venue": event["venue"],
        "starts_at": event["starts_at"].isoformat(),
        "is_flash_sale": event["is_flash_sale"],
        "available_seats": event["available_seats"],
        "total_seats": event["total_seats"],
    }

def reservation_to_json(reservation):
    return {
        "id": reservation["id"],
        "code": reservation_code(reservation["id"]),
        "created_at": reservation["created_at"].isoformat(),
        "event_id": reservation["event_id"],
        "seat_id": reservation["seat_id"],
        "section": reservation["section"],
        "seat_row": reservation["seat_row"],
        "seat_number": reservation["seat_number"],
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
    # Con ?section=<zona> devuelve solo las sillas de esa zona
    event = db.get_event(event_id)
    if event is None:
        return jsonify({"error": "Not Found", "message": "El evento no existe"}), 404

    section = request.args.get("section")
    if section is None:
        seats = db.list_seats(event_id)
    else:
        seats = db.list_section_seats(event_id, section)
        if len(seats) == 0:
            return jsonify({"error": "Not Found", "message": "La zona no existe en este evento"}), 404
    return jsonify(seats), 200

@app.route('/api/events/<int:event_id>/seats/<int:seat_id>/reserve', methods=['POST'])
def api_reserve_seat(event_id, seat_id):
    user = auth.get_current_user()
    if user is None:
        return jsonify({"error": "Unauthorized", "message": "Inicia sesión con POST /api/login"}), 401
    if not auth.csrf_token_is_valid(request.headers.get("X-CSRF-Token")):
        return jsonify({"error": "Forbidden", "message": "Token CSRF inválido o ausente"}), 403

    reservation = db.reserve_seat(event_id, seat_id, user["id"])
    if reservation is not None:
        return jsonify(reservation_to_json(reservation)), 201

    # No se reservó: o la silla no existe en este evento, o alguien la reservó antes
    if db.seat_exists(event_id, seat_id):
        return jsonify({"error": "Conflict", "message": "Esa silla ya fue reservada"}), 409
    return jsonify({"error": "Not Found", "message": "La silla no existe en este evento"}), 404

@app.route('/api/reservations')
def api_list_reservations():
    user = auth.get_current_user()
    if user is None:
        return jsonify({"error": "Unauthorized", "message": "Inicia sesión con POST /api/login"}), 401
    reservations = db.list_user_reservations(user["id"])
    return jsonify([reservation_to_json(reservation) for reservation in reservations]), 200

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
