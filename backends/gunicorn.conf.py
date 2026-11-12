import os

bind = f"0.0.0.0:{os.getenv('PORT', '5000')}"

# Workers y threads configurables por variable de entorno para comparar escenarios
workers = int(os.getenv("WEB_CONCURRENCY", "2"))
threads = int(os.getenv("GUNICORN_THREADS", "4"))

timeout = 30
accesslog = None
errorlog = '-'
loglevel = 'info'
