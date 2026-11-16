#!/usr/bin/env bash
# Prepara las condiciones iniciales de una corrida de Artillery.
#   verificar  Solo lee: revisa los servicios, los backends en HAProxy y las sillas libres.
#   reiniciar  Revisa los servicios, deja libres las sillas de prueba y vuelve a contar.
# No borra volúmenes ni usuarios, y no toca el evento agotado ("Cuentos de medianoche").
set -euo pipefail
cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.."

AGOTADO="Cuentos de medianoche"
SILLAS_MINIMAS="${SILLAS_MINIMAS:-2000}"

falla() { echo "ERROR: $*" >&2; exit 1; }

# Ejecuta en la base el SQL que llega por la entrada estándar.
sql() {
  docker compose exec -T db sh -c 'psql -X -q -t -A -v ON_ERROR_STOP=1 -U "$POSTGRES_USER" -d "$POSTGRES_DB"'
}

servicios() {
  echo "== Servicios =="
  for c in db backend1 backend2 backend3; do
    estado=$(docker inspect -f '{{.State.Health.Status}}' "$c" 2>/dev/null || echo "no existe")
    echo "$c: $estado"
    [ "$estado" = "healthy" ] || falla "$c no está healthy"
  done
  for c in haproxy datadog-agent; do
    estado=$(docker inspect -f '{{.State.Status}}' "$c" 2>/dev/null || echo "no existe")
    echo "$c: $estado"
    [ "$estado" = "running" ] || falla "$c no está running"
  done
  echo "== Backends en HAProxy =="
  estados=$(curl -fsS "http://localhost:8404/stats;csv" | awk -F, '$1=="be_app" && $2 ~ /^backend/ {print $2": "$18}')
  echo "$estados"
  [ "$(echo "$estados" | grep -c ': UP$')" -eq 3 ] || falla "HAProxy no ve los 3 backends en UP"
}

sillas() {
  echo "== Sillas por evento =="
  sql <<'SQL'
SELECT e.name || ' | ' || s.status || ' | ' || count(*)
FROM seats s JOIN events e ON e.id = s.event_id
GROUP BY e.id, e.name, s.status
ORDER BY e.id, s.status;
SQL
  libres=$(sql <<'SQL'
SELECT count(*) FROM seats s JOIN events e ON e.id = s.event_id
WHERE e.is_flash_sale AND s.status = 'available';
SQL
)
  echo "Sillas libres en el evento de venta flash: $libres (mínimo $SILLAS_MINIMAS)"
  [ "$libres" -ge "$SILLAS_MINIMAS" ] || falla "faltan sillas libres; corre: $0 reiniciar"
}

reiniciar_datos() {
  [ -z "$(docker ps -q --filter label=com.docker.compose.service=artillery)" ] \
    || falla "hay un contenedor de Artillery corriendo; espera a que termine"
  echo "== Reinicio de sillas (una sola transacción) =="
  sql <<SQL
BEGIN;
DELETE FROM reservations
WHERE seat_id IN (
  SELECT s.id FROM seats s JOIN events e ON e.id = s.event_id
  WHERE e.name <> '$AGOTADO'
);
UPDATE seats SET status = 'available'
WHERE status = 'reserved' AND id NOT IN (SELECT seat_id FROM reservations);
COMMIT;
SQL
  echo "Listo."
}

case "${1:-}" in
  verificar) servicios; sillas ;;
  reiniciar) servicios; reiniciar_datos; sillas ;;
  *) echo "Uso: $0 verificar|reiniciar" >&2; exit 2 ;;
esac