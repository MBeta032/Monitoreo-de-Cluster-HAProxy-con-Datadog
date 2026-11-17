# Prueba "Todos los backends caídos" · 16-nov-2026

**Quién:** Agente C (Probador). **Ventana:** 20:11:11 a 20:12:06 UTC (15:11:11 a 15:12:06 hora de Colombia, UTC-5).

## Pasos

1. Reparto previo: 30 `GET /api/info` seguidos a `http://localhost:8080`.
2. Tráfico bajo en segundo plano: 1 petición cada ~0,5 s (unas 1,3 req/s) a `/api/info`, con tope de 10 s por petición (`curl --max-time 10`), registrando código y tiempo total.
3. Estado de HAProxy cada segundo desde `http://localhost:8404/stats;csv`.
4. `docker compose stop backend1 backend2 backend3`, 15 s de espera, 3 `curl -w` de comprobación y una petición con cabeceras.
5. `docker compose start backend1 backend2 backend3`, espera a que estén `healthy` en Docker y `UP` en HAProxy, 10 s más de tráfico.
6. Reparto posterior: 30 `GET /api/info`.

Script usado: [`todos-caidos.sh`](todos-caidos.sh) (Bash y `curl`; no requiere nada más en el host).

## Línea de tiempo (UTC · local)

| Evento | UTC | Local | Tiempo |
|---|---|---|---|
| Orden `stop` de los 3 backends | 20:11:23.931 | 15:11:23 | 0 s |
| Primera respuesta de error (502, conexión cortada mientras Gunicorn se apagaba) | 20:11:25.335 | 15:11:25 | +1,4 s |
| Contenedores detenidos (fin de la orden) | 20:11:26.408 | 15:11:26 | +2,5 s |
| HAProxy marca `backend1` y `backend3` DOWN | 20:11:28.597 | 15:11:28 | +4,7 s |
| HAProxy marca los 3 DOWN (`BACKEND` DOWN) | 20:11:30.017 | 15:11:30 | +6,1 s |
| Orden `start` de los 3 backends | 20:11:42.083 | 15:11:42 | 0 s |
| Primer backend UP en HAProxy y primera respuesta 200 | 20:11:48.258 / 20:11:48.574 | 15:11:48 | +6,2 s / +6,5 s |
| Los 3 UP en HAProxy | 20:11:49.886 | 15:11:49 | +7,8 s |
| Los 3 `healthy` en Docker y UP en HAProxy | 20:11:52.632 | 15:11:52 | +10,5 s |

Corte visible para el cliente: de 20:11:25.3 a 20:11:48.5 (unos 23 s), con los backends detenidos unos 18 s.

## Resultados

| Indicador | Valor |
|---|---|
| Peticiones del tráfico bajo | 54: 32 × 200, 1 × 502, 21 × 503 |
| 503 con todos los backends DOWN (20 respuestas) | mínimo 5,7 ms · mediana 7,4 ms · máximo 18,5 ms |
| Petición más lenta | 1 × 503 en 4,016 s (empezó con los contenedores ya detenidos y antes de que HAProxy los marcara DOWN: intentos de conexión con `timeout connect 2s` + reintento) |
| Peticiones que llegaron al tope de 10 s (colgadas) | 0 |
| Cuerpo del 503 | `503 Service Unavailable · No server is available to handle this request.` (página propia de HAProxy) |
| Reparto antes / después (30 peticiones) | 10 / 10 / 10 · 10 / 10 / 10 |
| `haproxy/haproxy.cfg` | sin cambios (`git diff --exit-code` = 0) |
| Workers tras la prueba | 2 por backend (`WEB_CONCURRENCY=2`, 3 procesos Gunicorn: 1 maestro + 2 workers) |

**Conclusión:** con los 3 backends caídos HAProxy no se cuelga: responde 503 en milisegundos (mediana 7,4 ms) en cuanto marca los servidores DOWN (6,1 s tras la orden, coherente con `inter 1s fall 3`). Solo la ventana de detección deja una petición lenta (4 s) y un 502. Al volver, el primer backend atiende 6,5 s después de la orden `start` (`rise 2`) y el reparto vuelve a tercios exactos.

## Archivos

- `todos-caidos-linea-de-tiempo.txt`: marcas de tiempo, salida de `docker compose` y de `curl`.
- `todos-caidos-trafico.csv`: cada petición del tráfico bajo (hora UTC de fin, código, tiempo total, cuerpo).
- `todos-caidos-haproxy.csv`: estado de los 3 servidores y del backend `be_app` cada segundo.
- `todos-caidos-log-haproxy.txt`: líneas JSON 5xx del log de HAProxy en la ventana. Los 503 llevan `"server":"<NOSRV>"` y `termination_state` `SC`; la petición de 4 s lleva `queue_ms` 2001, `retries` `+2` y `total_ms` 4004.

## Contadores 5xx de HAProxy (pedido A-02 del Revisor)

Ver `../haproxy-contadores-5xx.txt`. Con 288 respuestas 5xx acumuladas en `be_app` (esta prueba más la de 2 backends), la fila `BACKEND` de `be_app` y la fila `FRONTEND` de `fe_web` cuentan `hrsp_5xx` = 288, mientras que **las 3 filas por servidor suman 0**. Los 503 sin servidor (`<NOSRV>`) solo se ven en las filas agregadas. Un widget o monitor que sume solo las series por servidor no ve estos 503.

## Efecto secundario detectado: IPs cruzadas en HAProxy

Al arrancar los 3 backends a la vez, Docker les dio otras IPs (backend1 .4 → .5, backend2 .6 → .4, backend3 .5 → .6). `haproxy.cfg` no tiene `resolvers`, así que HAProxy siguió usando las IPs del arranque: el servidor "backend1" apuntaba al contenedor backend2, etc. El servicio siguió funcionando (los 3 UP, reparto 10/10/10 por nombre de instancia), pero las etiquetas por servidor quedaron cruzadas. Se corrigió a las 20:23:15Z con `docker compose restart haproxy` con los 3 backends arriba. Detalle en `../hallazgo-ips-haproxy.txt`.
