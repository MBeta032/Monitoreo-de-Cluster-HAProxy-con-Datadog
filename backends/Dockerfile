FROM python:3.14-slim

# Crear usuario no root por seguridad
RUN groupadd -g 999 appgroup && \
    useradd -u 999 -g appgroup -s /bin/sh appuser

WORKDIR /app

# Instalar dependencias
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copiar código de la aplicación
COPY . .

# Asignar permisos al usuario no root
RUN chown -R appuser:appgroup /app

USER appuser

# Carpeta donde prometheus-client guarda las métricas de cada worker (modo multiproceso).
# gunicorn.conf.py la crea y la vacía al arrancar.
ENV PROMETHEUS_MULTIPROC_DIR=/tmp/prometheus_multiproc

EXPOSE 5000

# Healthcheck nativo sin instalar curl en la imagen
HEALTHCHECK --interval=5s --timeout=3s --start-period=5s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:5000/health')" || exit 1

CMD ["gunicorn", "-c", "gunicorn.conf.py", "app:app"]
