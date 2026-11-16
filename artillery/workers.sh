#!/usr/bin/env bash
# Compara 1, 2 y 4 workers de Gunicorn por backend con la misma rampa de carga (workers.yml).
#   bash artillery/workers.sh 1|2|4 [nombre]   recrea los backends con ese número de workers y corre la rampa
#   bash artillery/workers.sh restaurar         vuelve a los workers definidos en .env
# El número de workers se pasa por variable de entorno solo durante esta ejecución: no modifica .env.
set -euo pipefail
cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.."

ESCENARIO="${ESCENARIO:-workers.yml}"
IMAGEN_ARTILLERY="${IMAGEN_ARTILLERY:-artilleryio/artillery:2.0.34}"
STATS="http://localhost:8404/stats;csv"
LOG="${TMPDIR:-/tmp}/workers-artillery.log"
MODO="${1:-}"
SUFIJO="${2:-}"

# Git Bash en Windows convierte las rutas de Linux de los argumentos; se desactiva para docker run.
export MSYS_NO_PATHCONV=1
RAIZ="$(pwd -W 2>/dev/null || pwd)"

hora() { date -u +%H:%M:%S; }
falla() { echo "ERROR: $*" >&2; exit 1; }
estado() { curl -fsS "$STATS" | awk -F, -v s="$1" '$1=="be_app" && $2==s {print $18}'; }
hms() { date -u -d "@$1" +%H:%M:%S; }

case "$MODO" in
  1|2|4) N="$MODO" ;;
  restaurar) N="" ;;
  *) echo "Uso: $0 1|2|4 [nombre]   o   $0 restaurar" >&2; exit 2 ;;
esac
[ -f "artillery/$ESCENARIO" ] || falla "no existe artillery/$ESCENARIO"

esperar_backends_sanos() {
  local t=0
  until [ "$(for b in backend1 backend2 backend3; do docker inspect -f '{{.State.Health.Status}}' "$b" 2>/dev/null; done | grep -c '^healthy$')" -eq 3 ]; do
    sleep 2; t=$((t + 2))
    [ "$t" -lt 120 ] || falla "los backends no quedaron healthy en 120 s"
  done
}

esperar_haproxy_up() {
  local t=0
  until [ "$(for b in backend1 backend2 backend3; do estado "$b"; done | grep -c '^UP$')" -eq 3 ]; do
    sleep 1; t=$((t + 1))
    [ "$t" -lt 60 ] || falla "HAProxy no ve los 3 backends en UP en 60 s"
  done
}

echo "== Backends con ${N:-los workers de .env} =="
docker info --format 'Docker dispone de {{.NCPU}} CPU y {{.MemTotal}} bytes de memoria' 2>/dev/null || true
if [ -n "$N" ]; then
  export BACKEND1_WORKERS="$N" BACKEND2_WORKERS="$N" BACKEND3_WORKERS="$N"
else
  unset BACKEND1_WORKERS BACKEND2_WORKERS BACKEND3_WORKERS
fi
docker compose up -d --force-recreate backend1 backend2 backend3 >/dev/null 2>&1 || falla "no se pudieron recrear los backends"
esperar_backends_sanos
# HAProxy guarda las IP de los backends al arrancar: se reinicia para que vuelva a resolverlas (README, sección 4).
docker compose restart haproxy >/dev/null 2>&1 || falla "no se pudo reiniciar haproxy"
esperar_haproxy_up
for b in backend1 backend2 backend3; do
  p=$(docker top "$b" | grep -c gunicorn || true)
  echo "$b: $p procesos de Gunicorn (1 maestro y $((p - 1)) workers)"
  if [ -n "$N" ] && [ "$p" -ne $((N + 1)) ]; then falla "$b no tiene $N workers"; fi
done
if [ -z "$N" ]; then echo "Listo: backends con los workers de .env."; exit 0; fi

[ "$(docker inspect -f '{{.State.Status}}' datadog-agent 2>/dev/null)" = "running" ] || falla "datadog-agent no está running"
echo "Esperando 20 s a que los backends terminen de arrancar..."
sleep 20

echo "== Carga =="
docker rm -f artillery-workers >/dev/null 2>&1 || true
trap 'docker rm -f artillery-workers >/dev/null 2>&1 || true' EXIT
docker run --rm --name artillery-workers --network cluster-net \
  -v "$RAIZ/artillery:/scripts:ro" "$IMAGEN_ARTILLERY" run "/scripts/$ESCENARIO" >"$LOG" 2>&1 &
PID_ART=$!

t=0
until grep -q "Phase started" "$LOG"; do
  sleep 1; t=$((t + 1))
  kill -0 "$PID_ART" 2>/dev/null || { cat "$LOG"; falla "Artillery terminó antes de empezar"; }
  [ "$t" -lt 90 ] || falla "Artillery no arrancó en 90 s"
done
T0=$(date +%s)
echo "$(hora)  Rampa en marcha ($ESCENARIO): 6 minutos, de 2 a 12 usuarios virtuales por segundo."
wait "$PID_ART" || true
T1=$(date +%s)

echo; echo "== Resumen de Artillery =="
sed -n '/Summary report/,$p' "$LOG"

TITULO="workers-$N${SUFIJO:+-$SUFIJO}"
echo; echo "== Datos de la corrida: $N workers por backend (hora UTC) =="
echo "Inicio $(hms "$T0")   Fin $(hms "$T1")"
echo "Fase Baja hasta $(hms $((T0 + 120)))   Media hasta $(hms $((T0 + 240)))   Alta hasta el fin"
echo
echo "Para analizarla con las métricas de Datadog (espera 2 minutos a que lleguen las últimas):"
echo "docker run --rm -v \"\${PWD}:/app\" -w /app python:3.14-slim python artillery/analizar_datadog.py --inicio $(hms "$T0") --fin $(hms "$T1") --falla-desde $(hms $((T0 + 120))) --falla-hasta $(hms $((T0 + 240))) --nombres-fases Baja,Media,Alta --dia $(date -u +%F) --test workers --margen 120 --titulo $TITULO"