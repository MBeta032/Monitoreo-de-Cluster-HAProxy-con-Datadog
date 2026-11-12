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
