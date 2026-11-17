#!/usr/bin/env bash
# Prueba "Todos caídos": tráfico bajo (2 req/s a /api/info), se detienen los 3 backends, se mide el 503 y se recuperan.
# Uso: bash todos-caidos.sh <carpeta_salida>   (se ejecuta desde la raíz del repo)
set -uo pipefail
OUT="$1"; mkdir -p "$OUT"
TRAF="$OUT/todos-caidos-trafico.csv"; EST="$OUT/todos-caidos-haproxy.csv"; LOG="$OUT/todos-caidos-linea-de-tiempo.txt"
utc() { date -u +%H:%M:%S.%3N; }
loc() { date -u -d '-5 hours' +%H:%M:%S; }
marca() { echo "$(utc)Z | $(loc) local | $*" | tee -a "$LOG"; }

: > "$LOG"
echo "hora_utc,codigo,tiempo_total_s,cuerpo" > "$TRAF"
echo "hora_utc,backend1,backend2,backend3,BACKEND" > "$EST"

# 1) Reparto previo: 30 peticiones secuenciales
marca "Reparto previo: 30 GET /api/info"
for i in $(seq 1 30); do curl -s --max-time 5 http://localhost:8080/api/info; echo; done \
  | grep -o 'backend[0-9]' | sort | uniq -c | tee -a "$LOG"

# 2) Tráfico bajo en segundo plano (2 req/s, cada una con tope de 10 s)
( while [ ! -f "$OUT/.parar" ]; do
    r=$(curl -s -o "$OUT/.body" -w '%{http_code},%{time_total}' --max-time 10 http://localhost:8080/api/info)
    b=$(tr -d ',\n' < "$OUT/.body" | head -c 60)
    echo "$(utc),$r,$b" >> "$TRAF"; sleep 0.5
  done ) &
TPID=$!
# 3) Estado de HAProxy cada segundo
( while [ ! -f "$OUT/.parar" ]; do
    s=$(curl -s --max-time 2 "http://localhost:8404/stats;csv" | awk -F, '$1=="be_app"{printf ",%s",$18}')
    echo "$(utc)$s" >> "$EST"; sleep 1
  done ) &
SPID=$!

marca "Tráfico bajo iniciado (2 req/s a /api/info)"; sleep 10
marca "ORDEN: docker compose stop backend1 backend2 backend3"
docker compose stop backend1 backend2 backend3 2>&1 | tee -a "$LOG"
marca "Fin de la orden stop (contenedores detenidos)"
sleep 15
marca "Comprobación puntual con curl -w (3 peticiones)"
for i in 1 2 3; do curl -s -o /dev/null -w "  HTTP %{http_code} en %{time_total} s\n" --max-time 10 http://localhost:8080/api/info | tee -a "$LOG"; done
curl -s --max-time 10 -i http://localhost:8080/api/info | head -12 | tee -a "$LOG"
marca "ORDEN: docker compose start backend1 backend2 backend3"
docker compose start backend1 backend2 backend3 2>&1 | tee -a "$LOG"
marca "Fin de la orden start"
for i in $(seq 1 90); do
  h=$(for c in backend1 backend2 backend3; do docker inspect -f '{{.State.Health.Status}}' $c; done | grep -c '^healthy$')
  u=$(curl -s --max-time 2 "http://localhost:8404/stats;csv" | awk -F, '$1=="be_app" && $2 ~ /^backend/ && $18=="UP"' | wc -l)
  if [ "$h" -eq 3 ] && [ "$u" -eq 3 ]; then marca "3 backends healthy en Docker y UP en HAProxy"; break; fi
  sleep 1
done
sleep 10
touch "$OUT/.parar"; wait $TPID $SPID 2>/dev/null; rm -f "$OUT/.parar" "$OUT/.body"
marca "Tráfico detenido"
marca "Reparto posterior: 30 GET /api/info"
for i in $(seq 1 30); do curl -s --max-time 5 http://localhost:8080/api/info; echo; done \
  | grep -o 'backend[0-9]' | sort | uniq -c | tee -a "$LOG"
