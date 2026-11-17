# Plan de pruebas · cierre del Proyecto 8

Agente C (Probador) · 16-nov-2026, 15:05 a 15:30 (hora de Colombia, UTC-5). Regla: no repetir lo que Sharon y Juan José ya midieron; solo cubrir huecos.

Fuentes revisadas: `docs/evidencias/pruebas/Registro-de-pruebas.md`, README §10, `docs/evidencias/pruebas/0*/`, `docs/evidencias/carga-jj-20261114/`, `docs/evidencias/taquilla-20261115T021421969646Z/`, `reportes_datadog/`.

## 1. Mapa P1 a P5 y casos del balanceador

| Prueba | Ya cubierta por | Evidencia | Hueco | Qué voy a correr |
|---|---|---|---|---|
| P1 Dashboard en tiempo real | Nadie de forma completa (hay capturas parciales de Sharon: métricas de Artillery, CPU, peticiones/s) | `docs/evidencias/pruebas/0[1-4]-*/capturas/` | No hay captura del dashboard `nne-fkp-w5z` completo con tráfico | Ola 2: `normal.yml` (2 VU/s, 300 s) mientras el Orquestador captura (captura 02) |
| P2 Pico de Artillery visible en Datadog | Parcial: Sharon probó DogStatsD con `smoke-datadog.yml` y `errores.yml`; Juan José corrió `pico.yml` sin DogStatsD | Registro §2 y §3.3; `docs/evidencias/taquilla-*/` | Ninguna corrida de pico publica métricas en Datadog | Creado `artillery/pico-datadog.yml` (4 min, máx. 10 VU/s, `test:pico-datadog`), validado con 5 s. Corrida completa en Ola 2 con captura 03 |
| P3 Alerta al apagar un backend | **Sharon** (`falla.sh`, 2 corridas) | Registro §4; README §10.8 y §10.10; `docs/evidencias/pruebas/03-falla/capturas/` (correos y Datadog) | Ninguno | No se repite; solo en vivo en la demo con `falla.yml` (ver riesgo 3) |
| P4 Log Management | Nadie | Sin capturas. Solo instrucciones en README (§5.5, §10) | Consulta en Log Explorer y captura | Ola 2 (Orquestador, navegador): `service:haproxy @status_code:>=500` y `service:haproxy @server:backend2`. Comprobado hoy: el Agent recolecta el log de HAProxy (`Status: OK`) y los 503 sin servidor salen con `"server":"<NOSRV>"` |
| P5 Antes, durante y después | **Sharon** con datos (tabla README §10.10, `analizar_datadog.py`) | `reportes_datadog/caida-backend1-20261115T201207Z.html` y demás HTML | Falta la captura del timeline de Datadog con la ventana marcada | Ola 2: tras `pico-datadog.yml`, timeline con los eventos "Started/Finished" (captura 06) |
| Reparto entre 3 backends | Sharon (33/33/33 en stats y Datadog) | README §10.10; Registro §4.3 | Ninguno | Comprobado de paso: 30 `GET /api/info` → 10/10/10 antes y después de "todos caídos" |
| Caída de un backend | Sharon | Registro §4 | Ninguno | No se repite |
| Regreso de un backend | Sharon (UP en 4 a 9 s) | Registro §4.2 | Ninguno | No se repite |
| **Todos los backends caídos** | Nadie | — | Faltaba: debe dar 503 rápido, sin colgarse | **Corrida hoy** 15:11 local: ver `docs/evidencias/pruebas/05-entrega/todos-caidos/` |
| 2 backends con carga de pico | Nadie (pedido del Orquestador) | — | ¿Salen 503 con 10 VU/s y un backend caído? | **Corrida hoy** 15:14 local: ver `docs/evidencias/pruebas/05-entrega/validacion-2backends-10vus.txt` |
| Sesión pegajosa | No aplica: la sesión es una cookie firmada válida en los 3 backends (README §6.3) | README §6.3 | — | — |
| TLS, drenado de conexiones, backend lento | Fuera del alcance del proyecto (no hay HTTPS ni `slowstart`) | — | Mejora futura | — |

Revisión de casos con la skill `testing-load-balancers`: reparto, caída, regreso y todos caídos quedan cubiertos; sesión pegajosa no aplica; TLS, drenado y backend lento se dejan como mejora futura.

## 2. Resultados de hoy (resumen)

| Prueba | Resultado | Evidencia |
|---|---|---|
| Stack | 6 servicios arriba; `preparar_corrida.sh verificar` OK tras `reiniciar` (había 1 silla reservada: 1.999 de 2.000) | `docs/evidencias/pruebas/05-entrega/verificacion-stack.txt` |
| Validación de `pico-datadog.yml` (5 s a 1 VU/s, etiqueta aparte `test:validacion-pico`) | Sin `-e`: 5 de 5 VU fallan con `JJ_CREDENCIALES_AUSENTES`. Con la cuenta de prueba: 20/20 respuestas 200, 0 VU fallidos. El Agent recibió 4 paquetes de evento y 100 de métricas por DogStatsD, sin errores | `docs/evidencias/pruebas/05-entrega/validacion-pico-datadog.txt` |
| Todos caídos | 503 en 5,7 a 18,5 ms (mediana 7,4 ms) con los 3 DOWN; ninguna petición colgada; 1 petición de 4,0 s y un 502 durante la detección (6,1 s); vuelta a 200 a los 6,5 s del `start` | `docs/evidencias/pruebas/05-entrega/todos-caidos/README.md` |
| 2 backends a 10 VU/s (30 s) | **Falla**: 242 de 604 respuestas 503 (40 %), 258 de 300 VU fallidos. La CPU saturada hace vencer los chequeos de salud y HAProxy marca DOWN también a los sanos | `docs/evidencias/pruebas/05-entrega/validacion-2backends-10vus.txt` |
| Contadores 5xx (A-02) | `hrsp_5xx` de la fila `BACKEND` = 288; suma de las filas por servidor = 0 | `docs/evidencias/pruebas/05-entrega/haproxy-contadores-5xx.txt` |

## 3. Riesgos detectados

1. **`JJ_EMAIL` y `JJ_PASSWORD` llegan vacías al contenedor de Artillery** (no están definidas en `.env`). `normal.yml`, `pico.yml` y `pico-datadog.yml` fallan en todos los VU. Solución sin tocar `.env`: pasar la cuenta de prueba publicada en README §6.1 con `-e` (comandos abajo).
2. **IPs cruzadas tras reiniciar backends.** `haproxy.cfg` no tiene `resolvers`: si al volver un backend Docker le da otra IP, HAProxy sigue usando la vieja. Pasó hoy tras "todos caídos" (los 3 arrancaron a la vez). Se corrigió con `docker compose restart haproxy` con los 3 arriba. En la demo: arrancar Artillery **antes** de detener el backend y no crear contenedores nuevos (otra corrida de Artillery) mientras un backend está caído, porque el contenedor nuevo puede quedarse con la IP libre.
3. **No mezclar P3 con el pico.** Con un backend caído, 10 VU/s con login saturan a los otros dos. En la demo, la caída en vivo va con `falla.yml` (solo lectura, 20 req/s), como la midió Sharon.
4. Posibles alertas de Datadog entre 20:11 y 20:24 UTC (15:11 a 15:24 local) por estas pruebas de validación. No usar esa ventana para las capturas de P1, P2 ni P5.

## 4. Comandos listos para la Ola 2 (desde la raíz del repo, Git Bash o PowerShell)

Antes de cada corrida: `bash artillery/preparar_corrida.sh verificar` (si pide, `reiniciar`).

P2 · pico con Datadog (240 s, etiqueta `test:pico-datadog`):

```bash
docker compose --profile tools run --rm -e JJ_EMAIL=demo@taquilla.test -e 'JJ_PASSWORD=Taquilla2026!' artillery run /scripts/pico-datadog.yml -o /results/pico-datadog-$(date -u +%Y%m%dT%H%M%SZ).json
```

P1 · tráfico normal (300 s a 2 VU/s, sin DogStatsD):

```bash
docker compose --profile tools run --rm -e JJ_EMAIL=demo@taquilla.test -e 'JJ_PASSWORD=Taquilla2026!' artillery run /scripts/normal.yml -o /results/normal-$(date -u +%Y%m%dT%H%M%SZ).json
```

En PowerShell, cambia `$(date -u +%Y%m%dT%H%M%SZ)` por un nombre fijo (por ejemplo `pico-datadog-ola2.json`). Después de cada corrida: `git diff --exit-code haproxy/haproxy.cfg` y `docker compose ps`.

## 5. Nota para la demo: IP cruzadas en HAProxy

`haproxy.cfg` no tiene `resolvers`: HAProxy resuelve las IP de los backends solo al arrancar. Si se detienen los 3 backends juntos, Docker puede reasignarles otras IP al volver y las etiquetas de HAProxy y Datadog quedan cruzadas (por ejemplo, el servidor `backend1` apunta al contenedor `backend2`). Evidencia: [`hallazgo-ips-haproxy.txt`](../evidencias/pruebas/05-entrega/hallazgo-ips-haproxy.txt).

- Si se detuvieron los 3 backends juntos: con los 3 arriba y `healthy`, `docker compose restart haproxy`. Nunca reiniciar HAProxy con un backend apagado.
- En P3 se detiene y arranca **un solo** backend (`docker compose stop backend2` / `docker compose start backend2`), que conserva su IP.
- Antes de grabar: `docker compose restart haproxy` con los 3 backends arriba.
