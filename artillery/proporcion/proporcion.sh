#!/usr/bin/env bash
# Prueba de distribución de operaciones de consulta y reserva.
# Uso:
# ESCENARIO=proporcion-70-30.yml bash artillery/proporcion.sh

set -euo pipefail
cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.."

ESCENARIO="${ESCENARIO:-proporcion-50-50.yml}"
IMAGEN_ARTILLERY="${IMAGEN_ARTILLERY:-artilleryio/artillery:2.0.34}"
LOG="${TMPDIR:-/tmp}/proporcion-artillery.log"
RESULTADO=0

export MSYS_NO_PATHCONV=1
RAIZ="$(pwd -W 2>/dev/null || pwd)"

falla() {
  echo "ERROR: $*" >&2
  exit 1
}

# Solo permite los tres escenarios definidos para esta prueba.
case "$ESCENARIO" in
  proporcion-70-30.yml|proporcion-50-50.yml|proporcion-30-70.yml)
    ;;
  *)
    falla "Escenario no permitido: $ESCENARIO"
    ;;
esac

# Comprueba que las credenciales estén disponibles en el entorno.
[ -n "${ARTILLERY_EMAIL:-demo@taquilla.test}" ] || falla "Falta la variable ARTILLERY_EMAIL"
[ -n "${ARTILLERY_PASSWORD:-Taquilla2026!}" ] || falla "Falta la variable ARTILLERY_PASSWORD"

# Comprueba que no haya otra prueba de Artillery ejecutándose.
if docker ps -q --filter name=artillery-proporcion | grep -q .; then
  falla "Ya hay un contenedor artillery-proporcion ejecutándose"
fi

# Comprueba que HAProxy vea los tres backends activos.
STATS="http://localhost:8404/stats;csv"

estado() {
  curl -fsS "$STATS" |
    awk -F, -v s="$1" '$1=="be_app" && $2==s {print $18}'
}

echo "== Condiciones iniciales =="

for s in backend1 backend2 backend3; do
  [ "$(estado "$s")" = "UP" ] ||
    falla "HAProxy no ve $s en UP. Ejecuta preparar_corrida.sh verificar"
done

[ "$(docker inspect -f '{{.State.Status}}' datadog-agent 2>/dev/null)" = "running" ] ||
  falla "datadog-agent no está running"

echo "Los tres backends están UP."
echo "Datadog Agent está running."
echo "Escenario seleccionado: $ESCENARIO"

# Evita reutilizar el resultado de una ejecución anterior.
: > "$LOG"

limpiar() {
  docker rm -f artillery-proporcion >/dev/null 2>&1 || true
}
trap limpiar EXIT

echo
echo "== Ejecución de Artillery =="

if docker run --rm --name artillery-proporcion \
  --network cluster-net \
  --workdir /scripts \
  -e ARTILLERY_EMAIL \
  -e ARTILLERY_PASSWORD \
  -v "$RAIZ/artillery/proporcion:/scripts:ro" \
  "$IMAGEN_ARTILLERY" run "$ESCENARIO" >"$LOG" 2>&1; then
  RESULTADO=0
else
  RESULTADO=$?
fi

echo
echo "== Salida de Artillery =="

if [ "$RESULTADO" -eq 0 ]; then
  sed -n '/Summary report/,$p' "$LOG"
else
  cat "$LOG"
  echo "ERROR: Artillery terminó con código $RESULTADO"
fi

echo
echo "== Estado final en HAProxy =="

for s in backend1 backend2 backend3; do
  echo "$s: $(estado "$s")"
done

exit "$RESULTADO"
