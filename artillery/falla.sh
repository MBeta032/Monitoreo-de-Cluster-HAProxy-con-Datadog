#!/usr/bin/env bash
# Prueba de tolerancia a fallos: con carga constante, detiene un backend en el minuto 2 y lo
# vuelve a iniciar en el minuto 4. Artillery solo genera la carga; los contenedores los controla
# este script. Uso: bash artillery/falla.sh   (BACKEND=backend2 bash artillery/falla.sh para otro)
set -euo pipefail
cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.."

BACKEND="${BACKEND:-backend2}"
ESCENARIO="${ESCENARIO:-falla.yml}"
IMAGEN_ARTILLERY="${IMAGEN_ARTILLERY:-artilleryio/artillery:2.0.34}"
SEG_HASTA_PARADA=120   # minuto 2: se detiene el backend
SEG_PARADO=120         # minuto 4: vuelve a iniciarse
STATS="http://localhost:8404/stats;csv"
LOG="${TMPDIR:-/tmp}/falla-artillery.log"
RESULTADO=0

# Git Bash en Windows convierte las rutas de Linux de los argumentos; se desactiva para docker run.
export MSYS_NO_PATHCONV=1
RAIZ="$(pwd -W 2>/dev/null || pwd)"

hora() { date -u +%H:%M:%S; }
marca() { printf '%s  %s\n' "$(hora)" "$*"; }
falla() { echo "ERROR: $*" >&2; exit 1; }

# Estado y sesiones totales de un servidor de be_app, según la página de estadísticas de HAProxy.
estado()   { curl -fsS "$STATS" | awk -F, -v s="$1" '$1=="be_app" && $2==s {print $18}'; }
sesiones() { curl -fsS "$STATS" | awk -F, -v s="$1" '$1=="be_app" && $2==s {print $8}'; }

# Espera a que el estado del backend coincida con el patrón; imprime los segundos que tardó.
esperar_estado() {
  local patron="$1" limite="$2" t=0
  until estado "$BACKEND" | grep -Eq "$patron"; do
    sleep 1; t=$((t + 1))
    [ "$t" -lt "$limite" ] || return 1
  done
  echo "$t"
}

# Sesiones de los tres backends en un instante, y diferencia entre dos instantes.
snap() { for s in backend1 backend2 backend3; do printf '%s ' "$(sesiones "$s")"; done; echo; }
reparto() {
  read -r a1 a2 a3 <<<"$1"; read -r b1 b2 b3 <<<"$2"
  echo "backend1=$((b1 - a1)) backend2=$((b2 - a2)) backend3=$((b3 - a3))"
}

dormir_hasta() {  # segundos desde el inicio de la carga
  local falta=$(( T0 + $1 - $(date +%s) ))
  if [ "$falta" -gt 0 ]; then sleep "$falta"; fi
  return 0
}

# Pase lo que pase, el backend queda encendido y Artillery detenido.
limpiar() {
  docker compose start "$BACKEND" >/dev/null 2>&1 || true
  docker rm -f artillery-falla >/dev/null 2>&1 || true
}
trap limpiar EXIT

echo "== Condiciones iniciales =="
for s in backend1 backend2 backend3; do
  [ "$(estado "$s")" = "UP" ] || falla "HAProxy no ve $s en UP; corre antes: bash artillery/preparar_corrida.sh verificar"
done
[ "$(docker inspect -f '{{.State.Status}}' datadog-agent 2>/dev/null)" = "running" ] || falla "datadog-agent no está running"
echo "Los 3 backends están UP y el Agent está running."

echo "== Carga =="
docker rm -f artillery-falla >/dev/null 2>&1 || true
docker run --rm --name artillery-falla --network cluster-net \
  -v "$RAIZ/artillery:/scripts:ro" "$IMAGEN_ARTILLERY" run "/scripts/$ESCENARIO" >"$LOG" 2>&1 &
PID_ART=$!

t=0
until grep -q "Phase started" "$LOG"; do
  sleep 1; t=$((t + 1))
  kill -0 "$PID_ART" 2>/dev/null || { cat "$LOG"; falla "Artillery terminó antes de empezar"; }
  [ "$t" -lt 90 ] || falla "Artillery no arrancó en 90 s"
done
T0=$(date +%s); H_INICIO="$(hora)"
marca "Carga en marcha ($ESCENARIO). Se detendrá $BACKEND en el minuto 2."

dormir_hasta "$SEG_HASTA_PARADA"
marca "Deteniendo $BACKEND"
T_STOP=$(date +%s); H_STOP="$(hora)"
docker compose stop "$BACKEND" >/dev/null 2>&1
if S_DOWN=$(esperar_estado '^DOWN' 30); then
  S_DOWN=$(( $(date +%s) - T_STOP ))
  marca "HAProxy marca $BACKEND como DOWN (${S_DOWN} s después de la orden de detenerlo)"
else
  S_DOWN="no detectado"; RESULTADO=1
  marca "AVISO: HAProxy no marcó $BACKEND como DOWN en 30 s"
fi
A="$(snap)"; sleep 10; B="$(snap)"
marca "Reparto de sesiones en 10 s con $BACKEND caído: $(reparto "$A" "$B")"

dormir_hasta $(( SEG_HASTA_PARADA + SEG_PARADO ))
marca "Iniciando $BACKEND"
T_START=$(date +%s); H_START="$(hora)"
docker compose start "$BACKEND" >/dev/null 2>&1
if S_UP=$(esperar_estado '^UP' 90); then
  S_UP=$(( $(date +%s) - T_START ))
  marca "HAProxy marca $BACKEND como UP (${S_UP} s después de la orden de iniciarlo)"
  A="$(snap)"; sleep 10; B="$(snap)"
  R="$(reparto "$A" "$B")"
  marca "Reparto de sesiones en 10 s tras la recuperación: $R"
  case "$R" in *"$BACKEND=0 "*|*"$BACKEND=0") RESULTADO=1; marca "AVISO: $BACKEND volvió a UP pero no recibe tráfico" ;; esac
else
  S_UP="no detectado"; RESULTADO=1
  marca "AVISO: HAProxy no recuperó $BACKEND en 90 s (posible cambio de IP: ver README, sección 4)"
fi

wait "$PID_ART" || RESULTADO=1
H_FIN="$(hora)"

echo; echo "== Resumen de Artillery =="
sed -n '/Summary report/,$p' "$LOG"

echo; echo "== Línea de tiempo (UTC) =="
echo "Inicio de la carga ............... $H_INICIO"
echo "Orden de detener $BACKEND ....... $H_STOP"
echo "HAProxy lo marca DOWN ............ $S_DOWN s"
echo "Orden de iniciar $BACKEND ....... $H_START"
echo "HAProxy lo marca UP .............. $S_UP s"
echo "Fin de la carga .................. $H_FIN"

echo; echo "== Estado final en HAProxy =="
for s in backend1 backend2 backend3; do echo "$s: $(estado "$s")"; done
exit "$RESULTADO"