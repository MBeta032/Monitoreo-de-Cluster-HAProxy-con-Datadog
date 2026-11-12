import json
import logging
import os

from prometheus_client import multiprocess

bind = f"0.0.0.0:{os.getenv('PORT', '5000')}"

# Workers y threads configurables por variable de entorno para comparar escenarios
workers = int(os.getenv("WEB_CONCURRENCY", "2"))
threads = int(os.getenv("GUNICORN_THREADS", "4"))

timeout = 30
accesslog = None
errorlog = '-'
loglevel = 'info'


class GunicornJsonFormatter(logging.Formatter):
    # Mismos campos que los logs de la app (app.py) para que Datadog lea el nivel real
    def format(self, record):
        log_record = {
            "timestamp": int(record.created * 1000),
            "level": record.levelname,
            "message": record.getMessage(),
            "instance": os.getenv("INSTANCE_NAME", "backend-local"),
        }
        # Si Gunicorn registra una excepción, se agrega el detalle para no perderlo
        if record.exc_info:
            log_record["exception"] = self.formatException(record.exc_info)
        return json.dumps(log_record)


# Configuración de logs de Gunicorn (formato de logging.config.dictConfig).
# Gunicorn mezcla este diccionario con gunicorn.glogging.CONFIG_DEFAULTS.
logconfig_dict = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "json": {
            "()": GunicornJsonFormatter,
        },
    },
    "handlers": {
        "json_stdout": {
            "class": "logging.StreamHandler",
            "formatter": "json",
            "stream": "ext://sys.stdout",
        },
        "discard": {
            "class": "logging.NullHandler",
        },
    },
    "loggers": {
        # Mensajes del servidor (arranque, workers, errores) en JSON por stdout
        "gunicorn.error": {
            "level": "INFO",
            "handlers": ["json_stdout"],
            "propagate": False,
        },
        # Con logconfig_dict Gunicorn activa el access log aunque accesslog sea None;
        # se descarta para que /health y las peticiones no salgan en el log
        "gunicorn.access": {
            "level": "INFO",
            "handlers": ["discard"],
            "propagate": False,
        },
    },
    # Se reemplaza el root de CONFIG_DEFAULTS, que apunta a un handler que aquí no existe.
    # Queda igual al valor por defecto de Python: nivel WARNING y sin handlers.
    "root": {
        "level": "WARNING",
        "handlers": [],
    },
}


def on_starting(server):
    # Corre en el proceso maestro cada vez que arranca Gunicorn.
    # Vacía la carpeta de métricas: con "restart: unless-stopped" el contenedor
    # se reinicia sin recrearse y quedarían los archivos de la ejecución anterior.
    metrics_dir = os.environ["PROMETHEUS_MULTIPROC_DIR"]
    os.makedirs(metrics_dir, exist_ok=True)
    for file_name in os.listdir(metrics_dir):
        os.remove(os.path.join(metrics_dir, file_name))


def child_exit(server, worker):
    # Avisa a prometheus-client que este worker terminó (documentación oficial)
    multiprocess.mark_process_dead(worker.pid)
