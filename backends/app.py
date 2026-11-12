import os
import time
import json
import logging
import sys
from flask import Flask, jsonify, request, Response
from prometheus_client import Counter, Histogram, generate_latest, CONTENT_TYPE_LATEST

app = Flask(__name__)

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
        
        HTTP_REQUESTS_TOTAL.labels(method=method, handler=path, status=status_code).inc()
        HTTP_REQUEST_DURATION_SECONDS.labels(method=method, handler=path).observe(duration)
        
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

@app.route('/')
def index():
    instance_name = os.getenv("INSTANCE_NAME", "backend-local")
    return jsonify({
        "message": "Backend respondiendo correctamente",
        "instance": instance_name,
        "status": "success"
    }), 200

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
    return Response(generate_latest(), mimetype=CONTENT_TYPE_LATEST)

if __name__ == '__main__':
    port = int(os.getenv("PORT", 5000))
    app.run(host='0.0.0.0', port=port)
