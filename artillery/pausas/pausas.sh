#!/usr/bin/env bash
# tiempo entre acciones de un mismo usuario virtual.
#   bash artillery/pausas/pausas.sh sin|1a3|5s [nombre]
# Las tres variantes usan las mismas fases (30 s de calentamiento + 240 s estables a 3 usuarios/s)
# y las mismas peticiones por usuario; solo cambia la pausa. Es de solo lectura: no toca datos.
# No modifica .env ni los workers: corre con los que tengan los backends en ese momento.
set -euo pipefail
cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.."

IMAGEN_ARTILLERY="${IMAGEN_ARTILLERY:-artilleryio/artillery:2.0.34}"
RESULTADOS="${RESULTADOS:-docs/evidencias/pruebas/04-experimentos/resultados}"
STATS="http://localhost:8404/stats;csv"
MODO="${1:-}"
SUFIJO="${2:-}"

# Git Bash en Windows convierte las rutas de Linux de los argumentos; se desactiva para docker run.
export MSYS_NO_PATHCONV=1
RAIZ="$(pwd -W 2>/dev/null || pwd)"

hora() { date -u +%H:%M:%S; }
hms() { date -u -d "@$1" +%H:%M:%S; }
falla() { echo "ERROR: $*" >&2; exit 1; }

case "$MODO" in
  sin|1a3|5s) ;;
  *) echo "Uso: $0 sin|1a3|5s [nombre]" >&2; exit 2 ;;
esac

ESCENARIO="pausas/pausas-$MODO.yml"
TITULO="pausas-$MODO${SUFIJO:+-$SUFIJO}"
LOG="${TMPDIR:-/tmp}/$TITULO-artillery.log"
SALIDA="$RESULTADOS/$TITULO.txt"
CALENTAMIENTO=30   # s de la fase "calentamiento"
LLENADO=60         # s que tarda en llenarse el régimen estable (vida de un usuario con pausa de 5 s)
DURACION=270       # s de las dos fases de llegada de usuarios
[ -f "artillery/$ESCENARIO" ] || falla "no existe artillery/$ESCENARIO"
mkdir -p "$RESULTADOS"

echo "== Condiciones iniciales (solo lectura) =="
bash artillery/preparar_corrida.sh verificar
for b in backend1 backend2 backend3; do
  p=$(docker top "$b" | grep -c gunicorn || true)
  echo "$b: $((p - 1)) workers de Gunicorn"
done
[ "$(docker inspect -f '{{.State.Status}}' datadog-agent 2>/dev/null)" = "running" ] || falla "datadog-agent no está running"

echo "== Carga ($ESCENARIO) =="
docker rm -f artillery-pausas >/dev/null 2>&1 || true
trap 'docker rm -f artillery-pausas >/dev/null 2>&1 || true' EXIT
docker run --rm --name artillery-pausas --network cluster-net \
  -v "$RAIZ/artillery:/scripts:ro" "$IMAGEN_ARTILLERY" run "/scripts/$ESCENARIO" >"$LOG" 2>&1 &
PID_ART=$!

t=0
until grep -q "Phase started" "$LOG"; do
  sleep 1; t=$((t + 1))
  kill -0 "$PID_ART" 2>/dev/null || { cat "$LOG"; falla "Artillery terminó antes de empezar"; }
  [ "$t" -lt 90 ] || falla "Artillery no arrancó en 90 s"
done
T0=$(date +%s)
echo "$(hora)  En marcha: $DURACION s de llegada de usuarios; los últimos usuarios terminan unos segundos después."
wait "$PID_ART" || true
T1=$(date +%s)

{
  echo "== Resumen de Artillery ($TITULO) =="
  sed -n '/Summary report/,$p' "$LOG"
  echo
  echo "== Datos de la corrida (hora UTC) =="
  echo "Inicio $(hms "$T0")   Fin $(hms "$T1")"
  echo "Calentamiento hasta $(hms $((T0 + CALENTAMIENTO + LLENADO)))   Estable hasta $(hms $((T0 + DURACION)))   Cierre hasta el fin"
  echo
  echo "Para analizarla con Datadog (espera 2 minutos a que lleguen las últimas métricas):"
  echo "docker run --rm -v \"\${PWD}:/app\" -w /app python:3.14-slim python artillery/analizar_datadog.py --inicio $(hms "$T0") --fin $(hms "$T1") --falla-desde $(hms $((T0 + CALENTAMIENTO + LLENADO))) --falla-hasta $(hms $((T0 + DURACION))) --nombres-fases Calentamiento,Estable,Cierre --dia $(date -u +%F) --test pausas-$MODO --margen 120 --titulo $TITULO"
} | tee "$SALIDA"
echo
echo "Resultado guardado en $SALIDA"