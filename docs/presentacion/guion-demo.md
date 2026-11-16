# Guion de la presentación y la demo · Proyecto 8

**Monitoreo de clúster HAProxy con Datadog** · Servicios Telemáticos · UAO 2026-2

> Estado: **borrador Ola 1** (Agente G, 16-nov-2026 15:05). Los tiempos marcados con `[CONFIRMAR EN ENSAYO]` se ajustan con el ensayo seco del Agente C (Ola 2). Límite: guion cerrado a las 5:30 p. m.; grabación antes de las 7:00 p. m.
>
> Regla de pantalla: **`.env` nunca aparece** (ni `cat .env`, ni `docker compose config` sin `--quiet`, ni `docker inspect datadog-agent`, ni `agent status`, porque muestran o insinúan claves). Tampoco se abre la bandeja de correo en vivo: los correos personales salen en las capturas de Plan B.

---

## 1. Reparto de los 20 minutos

| Tramo | Bloque | Min | Quién habla | De qué habla (y por qué esa persona) |
|---|---|:-:|---|---|
| 0:00 a 2:00 | Problema y requisitos | 2 | **Manuel** (Infraestructura y HAProxy) | La Taquilla Sucursal: venta de sillas que no puede caerse en una venta flash. Qué pide el cliente (PDF, Partes 1 a 3, P1 a P5) y qué significa "sin nada instalado en el equipo" |
| 2:00 a 5:00 | Alternativas y matrices | 3 | **Juan José** 1:15 · **Esteban** 1:00 · **Jhon** 0:45 | JJ: HAProxy y Datadog como restricción del cliente + matriz Round Robin frente a LeastConn (su campaña). Esteban: matriz de 1, 2 y 4 workers de Gunicorn (datos de Sharon sobre sus backends). Jhon: cómo lee el Agent a HAProxy (socket Unix) y formato de logs (JSON) |
| 5:00 a 7:00 | Arquitectura | 2 | **Manuel** 0:45 · **Esteban** 0:35 · **Jhon** 0:40 | Manuel: Compose, red `cluster-net`, HAProxy 2.6, health checks (`inter 1s fall 3 rise 2`). Esteban: 3 backends Flask + Gunicorn con PostgreSQL 17, límite 1 CPU y 384 MB. Jhon: Agent 7.85.1 por socket, logs JSON por stdout, DogStatsD para Artillery |
| 7:00 a 14:00 | **Demo** (video grabado hoy) | 7 | **Alan** (P1), **Juan José** (P2), **Sharon** + Alan (P3), **Jhon** (P4), **Sharon** (P5) · operador del teclado: Manuel | Ver la tabla de la sección 2 |
| 14:00 a 17:00 | Resultados y discusión | 3 | **Sharon** 1:15 · **Esteban** 0:45 · **Juan José** 0:30 · **Alan** 0:30 | Sharon: caída y errores controlados. Esteban: workers y límite de CPU, concurrencia en la misma silla. JJ: dónde se degrada el clúster (10 frente a 20 VU/s). Alan: tiempos de detección de los monitores y su porqué |
| 17:00 a 20:00 | Preguntas | 3 | **Manuel** modera; responde quien aparece en la sección 4 | Banco de 10 preguntas con respuesta corta |

Tiempo de voz aproximado por persona (sin preguntas): Manuel 2:45 + operador de la demo · Juan José 3:30 · Esteban 2:20 · Jhon 2:25 · Alan 2:15 · Sharon 3:20. `[CONFIRMAR EN ENSAYO]`

### 1.1 Frases guía por bloque (no leer; son el hilo)

- **Problema (Manuel):** "Si en una venta flash se cae un servidor, el cliente no se entera hasta que llaman los usuarios. Queremos que el clúster lo absorba solo y que el equipo lo vea en menos de un minuto, con datos."
- **Alternativas (JJ, Esteban, Jhon):** "HAProxy y Datadog los fija el cliente; donde sí había opción, decidimos con matrices y con datos medidos por nosotros." Cifras en la sección 5 (de dónde sale cada una).
- **Arquitectura (Manuel, Esteban, Jhon):** usar la Fig. 1 (diagrama de `docs/diagramas/`, Agente D o E) o el diagrama Mermaid de README §1.
- **Resultados (Sharon, Esteban, JJ, Alan):** "Cada número que vieron en la demo ya lo habíamos medido con repeticiones; aquí está la tabla."

---

## 2. Demo de 7 minutos (P1 a P5)

**Montaje:** el operador (Manuel) maneja teclado y ratón; quien narra no toca nada. Terminales en **PowerShell**, dentro de `C:\proyectos\Monitoreo-de-Cluster-HAProxy-con-Datadog`. Chrome con la sesión de Datadog y las pestañas en el orden de la sección 3.2.

**Carga de la demo:** `artillery/pico-datadog.yml` (lo crea el Agente C a partir de `pico.yml` con el bloque `publish-metrics` de `smoke-datadog.yml`). Si conserva las fases de `pico.yml` (120 s a 2 VU/s, 60 s de subida a 10, 180 s a 10, 60 s de bajada, 120 s a 2; total 540 s), al lanzarla en el minuto 0:30 de la demo: base hasta 2:30, subida 2:30 a 3:30, **meseta 3:30 a 6:30**, bajada desde 6:30 y fin (evento "Finished") en 9:30, después de cortar el video. `[CONFIRMAR EN ENSAYO]` duración real y etiqueta (se asume `test:pico-datadog`).

Se lanza con el servicio `artillery` de Compose (perfil `tools`) porque `pico.yml` usa `taquilla.js`, que necesita `JJ_EMAIL` y `JJ_PASSWORD`: Compose los toma de `.env` sin mostrarlos.

| Minuto | Quién habla | Qué se ve | Comando o clic exacto | Qué decir (1 frase) | Plan B si falla |
|:-:|---|---|---|---|---|
| **P1** 0:00 | Alan | Terminal 1: lista de contenedores | `docker compose ps` | "Todo el sistema son seis contenedores en Docker Compose: HAProxy, tres backends, PostgreSQL y el Agent de Datadog; en el equipo no hay nada más instalado." | Si falta alguno: `docker compose up -d` y seguir hablando 30 s; si no sube, cortar la toma y retomar desde aquí |
| 0:15 | Alan | Terminal 1: seis respuestas `{"instance":"backendN"}` en orden 1, 2, 3, 1, 2, 3 | `1..6 \| % { curl.exe -s http://localhost:8080/api/info }` | "Seis peticiones seguidas al puerto 8080 y HAProxy las reparte por turnos: Round Robin." | Mostrar README §4 paso 6 (resultado esperado) y seguir |
| 0:30 | Juan José | Terminal 1: Artillery arranca ("Phase started") | `docker compose --profile tools run --rm artillery run /scripts/pico-datadog.yml -o /results/pico-datadog-demo.json` | "Lanzo el pico desde un contenedor aparte; empieza suave, con 2 usuarios nuevos por segundo, que es nuestro tráfico normal." | Si sale `JJ_CREDENCIALES_AUSENTES` o no arranca en 15 s: `docker run --rm --network cluster-net -v "${PWD}/artillery:/scripts:ro" artilleryio/artillery:2.0.34 run /scripts/falla.yml` (carga sin login, 30 req/s, publica evento "Artillery falla"; Registro §4) |
| 0:45 | Alan | Chrome pestaña 1: página de estadísticas, `backend1` a `backend3` en verde, `LastChk L7OK/200` | Clic en pestaña 1 (`http://localhost:8404/stats`) | "HAProxy pregunta `/health` a cada backend cada segundo; los tres están UP." | Captura 09 si existe; si no, README §5.3 |
| 1:00 | Alan | Pestaña 2: dashboard `nne-fkp-w5z`, grupos 1 Estado (semáforos verdes, 5xx en verde) y 2 Tráfico | Clic en pestaña 2; rango **Past 15 minutes**; desplazar a grupo 2 | "Este es el P1: el mismo estado, pero en Datadog, con historial; cada 5 s el Agent lee el socket de HAProxy." | Captura 02 `docs/evidencias/pruebas/05-entrega/capturas/02-dashboard-completo.png` `[CONFIRMAR nombre con Orq]`; enlace público de README §8 |
| **P2** 1:30 | Juan José | Pestaña 3: Event Management con el evento "Artillery pico-datadog" (Started) | Clic en pestaña 3; buscar `tags:test:pico-datadog` (si no filtra: `Artillery`) | "Artillery no tiene la API key: manda sus métricas y este evento al Agent por DogStatsD, y así marca en Datadog cuándo empezó la prueba." | Captura `docs/evidencias/pruebas/01-integracion-datadog/capturas/datadog-artillery-eventos.jpg` (smoke de Sharon) |
| 2:00 | Juan José | Pestaña 2: grupo 2 Tráfico (peticiones/s) y grupo 3 Tiempo de espera (p50/p95/p99 de `@total_ms`) | Clic en pestaña 2; desplazar a grupos 2 y 3 | "En 2:30 empieza la subida de 2 a 10 usuarios por segundo; miren cómo sube la curva de HAProxy al mismo tiempo que la de Artillery." | Captura 03 (pico con evento) `[CONFIRMAR nombre con Orq]`; si no, `docs/evidencias/pruebas/02-errores/capturas/datadog-errores-metricas.jpeg` |
| 2:45 | Juan José | Pestaña 7 (opcional): `artillery.http.request_rate{test:pico-datadog}` | Clic en pestaña 7 (Metrics Explorer ya cargado) | "Es la misma corrida vista desde el generador: la correlación entre carga y métricas que pide el P2." | Saltar esta fila si el tiempo va justo `[CONFIRMAR EN ENSAYO]` |
| **P3** 3:15 | Sharon | Terminal 2: `backend2` detenido | `docker compose stop backend2` | "Ahora, con el pico subiendo, apago `backend2` como si se cayera el servidor." | Si la orden no responde en 10 s: `docker stop backend2` |
| 3:25 | Sharon | Pestaña 1: `backend2` en rojo, `DOWN` | Clic en pestaña 1 (se recarga sola cada 5 s) | "HAProxy lo saca en unos 5 segundos: tres chequeos fallidos de un segundo; Sharon lo midió en 5 y 6 s." | `docs/evidencias/pruebas/03-falla/capturas/datadog-caida-backend2.jpeg` |
| 3:40 | Sharon | Pestaña 2: grupo 1 (semáforo de `backend2` en rojo) y grupo 6 Reparto (`backend2` cae a 0; los otros dos suben) | Clic en pestaña 2; desplazar a grupos 1 y 6 | "El tráfico de `backend2` se va a los otros dos: en nuestra corrida medida el reparto pasó de 33/33/33 a 1/49/49 y el servicio no se cortó." | `docs/evidencias/pruebas/03-falla/capturas/datadog-peticiones-por-segundo.jpeg` + Registro §4.3 |
| 4:15 | Alan | Pestaña 4: monitor `342430447` en **[Triggered]** con `backend:backend2` | Clic en pestaña 4; recargar (F5) | "El monitor necesita dos lecturas seguidas en CRITICAL más la evaluación de Datadog: suena alrededor de 60 s después de la caída, y avisa por correo al Team." | Si aún no sale: esperar 15 s hablando del correo; si no, `docs/evidencias/pruebas/03-falla/capturas/correo-caida-backend.jpeg` y README §10.10 (20:15:07 UTC, 60 s) |
| 4:35 | Sharon | Terminal 2 y pestaña 1: `backend2` vuelve a verde | `docker compose start backend2` y clic en pestaña 1 | "Lo enciendo: vuelve en 4 a 9 segundos, cuando pasa dos chequeos seguidos." | Si no vuelve a UP en 20 s: `docker compose restart haproxy` (README §10.8) |
| **P4** 5:00 | Jhon | Pestaña 5: Log Explorer con logs JSON de HAProxy y sus atributos (`@status_code`, `@server`, `@total_ms`) | Clic en pestaña 5; en la búsqueda: `service:haproxy @status_code:>=500`; rango Past 15 minutes | "Cada petición deja una línea JSON y Datadog la parte en atributos sin pipeline; aquí buscamos solo los 5xx." Si sale vacío o 1: "Con `redispatch` casi no hay 5xx: en la caída medida hubo 1 de 6.975." | Cambiar el rango al 15-nov 12:39 a 12:47 (hora Cali; errores controlados de Sharon, 213 respuestas 500) `[CONFIRMAR EN ENSAYO que los logs sigan retenidos]`; si el rango numérico no filtra: `service:haproxy @status_code:[500 TO 599]` |
| 5:30 | Jhon | Pestaña 5 (o 6): hueco en los logs de `backend2` entre la caída y el regreso | Escribir `service:haproxy @server:backend2` (o pestaña 6 ya cargada) | "Este es el hueco de `backend2`: no recibió tráfico mientras estuvo caído, y vuelve justo cuando lo encendimos." | Captura 05 Log Explorer `[CONFIRMAR nombre con Orq]` |
| **P5** 6:00 | Sharon | Pestaña 2: dashboard Past 15 minutes, grupos 2, 3 y 6: **antes** (base de 2 VU/s, tercios), **durante** (pico + caída, dos backends), **después** (`backend2` de vuelta, tercios) | Clic en pestaña 2; arrastrar el ratón sobre la gráfica para señalar las tres zonas | "Antes, durante y después en la misma línea de tiempo: carga de Artillery, reparto de HAProxy y tiempo de respuesta." | Abrir `reportes_datadog\caida-backend1-20261115T201207Z.html` (fases sombreadas, `analizar_datadog.py`) `[CONFIRMAR ruta: el Agente B podría mover la carpeta]` + captura 06 |
| 6:30 | Sharon | Pestaña 4: historial del monitor, Triggered y luego Recovered (≈ 60 s después de encender) | Clic en pestaña 4; F5 | "Y la alerta se cerró sola cuando `backend2` volvió: el ciclo completo quedó registrado." | README §10.10: `[Recovered]` 60 s tras la orden de iniciar |
| 6:50 | Manuel | Pestaña 2 | Ninguno | "Esos son P1 a P5 en vivo; las cifras con repeticiones están en el informe." | Cortar la toma |

### 2.1 Notas de tiempo y riesgos de la demo

- **Ventana del monitor:** apagar `backend2` justo al empezar P3 (3:15). El minuto de espera se llena con la página de estadísticas (3:25) y el reparto en el dashboard (3:40). `[CONFIRMAR EN ENSAYO]` si el `[Triggered]` sale antes de 4:15.
- **Retraso de Datadog:** las métricas y eventos tardan entre 15 s y 1 min en verse (README §10.4 recomienda esperar 1 a 2 min tras cada corrida). Por eso el evento "Started" se busca 1 min después de lanzar la carga. `[CONFIRMAR EN ENSAYO]`
- **Capacidad con dos backends en el pico:** `pico.yml` hace login en cada usuario (hash de contraseña, unos 300 ms de CPU, Registro §3.2). La campaña de JJ con login dio 100 % de flujos a 10 VU/s y 39,17 % a 20 VU/s (`docs/evidencias/taquilla-20261115T021421969646Z/cierre-verificado.md`). Con dos backends la meseta de 10 VU/s podría producir algunos 503. Si sale en el ensayo, se dice tal cual en P4: "con un servidor menos, el pico se reparte en 2 CPU en lugar de 3; por eso el monitor de 5xx existe". `[CONFIRMAR EN ENSAYO]`
- **Si la toma se cae a mitad:** `docker compose start backend2`, esperar a que termine Artillery (o `docker compose ps -a` y borrar el contenedor de la corrida con `docker rm -f <nombre>`), `& "C:\Program Files\Git\bin\bash.exe" artillery/preparar_corrida.sh verificar` y volver a grabar desde 0:00. Una repetición completa cuesta unos 12 min (7 de demo + 5 de espera para que el monitor vuelva a OK y la carga termine). `[CONFIRMAR EN ENSAYO]`

---

## 3. Antes de grabar

### 3.1 Checklist (en este orden, 15 minutos antes)

| # | Qué | Cómo | Debe verse |
|:-:|---|---|---|
| 1 | Nadie más está corriendo cargas | Preguntar al Orquestador y a C; `docker ps --filter ancestor=artilleryio/artillery:2.0.34` | Lista vacía |
| 2 | HAProxy con su configuración real | `git diff --exit-code haproxy/haproxy.cfg` | Sin salida (código 0). Si hay cambios: avisar al Orquestador, no grabar |
| 3 | Backends con 2 workers | Si alguien usó `workers.sh`: `& "C:\Program Files\Git\bin\bash.exe" artillery/workers.sh restaurar` | Termina sin error |
| 4 | Docker arriba y sano | `docker compose ps` | `db`, `backend1`, `backend2`, `backend3` en `(healthy)`; `haproxy` y `datadog-agent` arriba |
| 5 | Sistema listo | `& "C:\Program Files\Git\bin\bash.exe" artillery/preparar_corrida.sh verificar` | 3 backends `UP` y 2.000 sillas libres |
| 6 | Monitores en OK | Pestaña 4 y Monitors → Manage | `342430447`, `342430701` y `344613789` en OK (si alguno sigue en alerta por el ensayo, esperar) |
| 7 | Sesión de Datadog abierta | Chrome, pestaña solo de Datadog | Dashboard carga datos (no "Loading") |
| 8 | Pestañas en orden | Sección 3.2 | Cada una cargada y con su filtro escrito |
| 9 | Terminales listas | Dos ventanas de PowerShell en la carpeta del repo, letra grande (Ctrl + rueda, unos 20 pt), historial limpio (`Clear-Host`) | Comandos de la demo **escritos en un bloc aparte**, no en el historial |
| 10 | `.env` fuera de la vista | Cerrar el editor o cualquier pestaña con `.env`; no correr `docker compose config` sin `--quiet`, `docker inspect datadog-agent` ni `agent status` | Nada con claves en pantalla |
| 11 | Correo personal fuera de la vista | Bandeja cerrada; avatar y menú de usuario de Datadog sin abrir | Solo se muestran correos por capturas |
| 12 | Memoria libre | Cerrar Teams, WhatsApp, otros Chrome, VS Code si no se usa (12 GB de RAM; la VM de Docker tiene 4,74 GiB, `datos-medidos.md`) | Administrador de tareas con más de 1,5 GB libres |
| 13 | Grabador | Pantalla completa, micrófono probado 10 s, notificaciones de Windows en "No molestar" | Prueba de 10 s se oye bien |
| 14 | Hora | Reloj visible o anotado; Datadog en hora de Cali (UTC−5) | Se anota la hora de inicio para el informe (P5) |

### 3.2 Orden de pestañas y ventanas

| # | Dónde | Qué queda cargado |
|:-:|---|---|
| T1 | PowerShell 1 (carga) | Carpeta del repo, pantalla limpia |
| T2 | PowerShell 2 (caída) | Carpeta del repo, pantalla limpia |
| 1 | Chrome | `http://localhost:8404/stats` |
| 2 | Chrome | `https://app.datadoghq.com/dashboard/nne-fkp-w5z`, rango Past 15 minutes, filtro `backend` en todos |
| 3 | Chrome | Event Management → All Events (`https://app.datadoghq.com/event/explorer`), búsqueda `tags:test:pico-datadog` escrita |
| 4 | Chrome | `https://app.datadoghq.com/monitors/342430447` |
| 5 | Chrome | Log Explorer (`https://app.datadoghq.com/logs`) con `service:haproxy @status_code:>=500` |
| 6 | Chrome | Log Explorer con `service:haproxy @server:backend2` |
| 7 | Chrome (opcional) | Metrics Explorer con `artillery.http.request_rate{test:pico-datadog}` |
| 8 | Explorador de archivos (Plan B) | `docs\evidencias\pruebas\03-falla\capturas\` y `docs\evidencias\pruebas\05-entrega\capturas\` |

---

## 4. Banco de 10 preguntas probables

| # | Pregunta | Responde | Respuesta corta | De dónde sale el dato |
|:-:|---|---|---|---|
| 1 | ¿Por qué Round Robin si LeastConn dio un p95 menor? | Juan José | Con 20 VU/s y 300 s, RR dio p95 de 3, 3 y 4 ms y LeastConn de 3, 2 y 2 ms; en la taquilla con login, RR 106,7 / 111,1 / 106,7 ms y LeastConn 108,9 / 108,9 / 111,1 ms. Son diferencias de menos de 5 ms, en orden fijo y con 3 repeticiones: no hay ganador claro y los backends son idénticos con peticiones cortas, así que se dejó el más simple | `docs/evidencias/carga-jj-20261114/informe.md`; `docs/evidencias/taquilla-20261115T021421969646Z/cierre-verificado.md`; README §5.6; matriz del Agente D `[CONFIRMAR con docs/matrices/matrices.md]` |
| 2 | Si HAProxy detecta la caída en 5 s, ¿por qué la alerta tarda 60 s? | Alan | HAProxy marcó DOWN a los 5 s; el Agent lee el socket cada 5 s y el monitor exige 2 lecturas seguidas en CRITICAL, más la evaluación y el envío de Datadog: `[Triggered]` a los 60 s. Es a propósito: una sola lectura mala no despierta a nadie | README §10.10 (20:14:07 orden, 20:14:12 DOWN, 20:15:07 Triggered); README §8.2; `min_collection_interval: 5` en `datadog/conf.d/haproxy.d/conf.yaml` |
| 3 | ¿Se perdieron peticiones cuando se cayó el backend? | Sharon | Casi ninguna: 1 respuesta 502 de 6.975 (99,986 % de 200) a 20 req/s y 1 de 10.425 a 30 req/s; la más lenta tardó unos 2 s. Coincide con `timeout connect 2s` y `option redispatch`, aunque no se comprobó que sea la causa directa | Registro §4.4; README §10.10; `haproxy/haproxy.cfg` |
| 4 | ¿Por qué el Agent lee un socket Unix y no la página de estadísticas? | Jhon | Lo pide el enunciado; además el socket va en un volumen compartido, con `mode 660` y `level user` (solo lectura) y no abre puertos; la página 8404 solo se publica en `127.0.0.1`. Desventaja honesta: Datadog marca el modo socket como antiguo (`use_openmetrics: false`) | README §5.2 y §5.4; `datadog/conf.d/haproxy.d/conf.yaml`; matriz del Agente D `[CONFIRMAR]` |
| 5 | ¿Cómo prueban que lo que ve Datadog corresponde a la carga de Artillery? | Juan José | Artillery publica por DogStatsD con la etiqueta `test:<escenario>` y eventos de inicio y fin. En el smoke, 40 peticiones en Artillery y 40 en Datadog; en errores (corrida B) 2.299 en Artillery y 2,30 k en Datadog, y cada código coincide (105, 109, 211, 211) | Registro §2.1 y §3.3; README §10.5 |
| 6 | ¿Por qué 2 workers por backend y no 4? | Esteban | Con 4 workers baja el p95 global (727,9 frente a 3.072,4 ms) pero los 503 siguen igual (60,49 % frente a 61,35 %), la CPU queda cerca de 1 núcleo (0,97 a 1,0) en la fase alta con las tres configuraciones y la memoria sube a 174 a 187 MB. El cuello es la CPU de 1 núcleo, no el número de procesos | Registro §5.3.2 y §5.3.3; README §10.13; decisión final según la matriz del Agente D `[CONFIRMAR]` |
| 7 | ¿Cuánta carga aguanta el clúster? | Juan José | Con login en cada usuario: a 10 VU/s el 100 % de los flujos terminó (p95 228,2 ms, 0 errores 5xx); a 20 VU/s solo el 39,17 % (3.634 respuestas 5xx). El límite está entre 10 y 20 VU/s en este equipo; el login cuesta unos 300 ms de CPU | `docs/evidencias/taquilla-20261115T021421969646Z/cierre-verificado.md`; Registro §3.2 |
| 8 | ¿Qué pasa si se caen los tres backends? | Manuel | HAProxy responde 503 de inmediato (servidor `<NOSRV>` en el log) en lugar de dejar colgado al cliente, y el cliente misterioso (`344613789`) y el monitor de 5xx avisan | `[CONFIRMAR con la prueba "todos caídos" del Agente C hoy]`; README §5.5 (`<NOSRV>`) y §8.2 |
| 9 | ¿Por qué logs en JSON y no syslog de texto? | Jhon | Datadog convierte cada campo en atributo sin escribir un pipeline: con `@total_ms` se calculan p50, p95 y p99 del dashboard y con `@server` se filtra por backend, como en P4. Los campos que manda el cliente se escapan y se recortan (512 y 32 bytes) para que el JSON no se rompa | README §5.5 y §8.1; `haproxy/haproxy.cfg` (`log-format`); matriz del Agente D `[CONFIRMAR]` |
| 10 | ¿Dónde están las claves y cómo evitan filtrarlas? | Sharon | Solo en `.env`, que está en `.gitignore`. Solo el Agent recibe `DD_API_KEY`; Artillery no la tiene porque publica al Agent por DogStatsD (puerto 8125 sin publicar). La contraseña de PostgreSQL para el Agent va con `%%env_DD_POSTGRES_PASSWORD%%`. Antes de entregar se revisa el historial con Gitleaks | README §7.10, §10.5 y §10.14; `docker-compose.yml`; `.gitleaks.toml` |

**Dos preguntas difíciles (respuesta honesta preparada):**
- *"El dashboard mostró 0 % de 5xx en la campaña de JJ y Artillery recibió miles de 503."* (Alan) Es una discrepancia registrada y abierta: la consulta usa `haproxy.backend.response.5xx` sin la fila del grupo, y los 503 que genera el propio HAProxy podrían no contarse ahí. Es una hipótesis, no una causa comprobada. Fuente: `cierre-verificado.md`, sección "Discrepancias de monitoreo pendientes". `[CONFIRMAR si el Agente A o C la cerraron hoy]`
- *"¿Hay algo instalado fuera de Docker?"* (Manuel) La carga corre en contenedor; los `.sh` usan Git Bash y `curl`, que vienen con Git for Windows. Los scripts de análisis en Python se ejecutan con `docker run python:3.14-slim` (README §10.9). `[CONFIRMAR con los arreglos del Agente B]`

---

## 5. Cifras que se dicen en voz alta (fuente única)

| Cifra | Dónde se dice | Fuente |
|---|---|---|
| DOWN en 5 a 6 s, UP en 4 a 9 s | Demo P3, Resultados | Registro §4.2 |
| `[Triggered]` a 60 s y `[Recovered]` a 60 s | Demo P3/P5, pregunta 2 | README §10.10 |
| Reparto 33/33/33 → 1/49/49 → 31/34/34 | Demo P3, Resultados | README §10.10 |
| p95 9,3 → 175,7 → 7,9 ms | Resultados | README §10.10 |
| 1 de 6.975 con 502 | Demo P4, pregunta 3 | Registro §4.4 |
| 9,3 % de 5xx; `[Warn]` 1 min 46 s, `[Triggered]` 2 min 46 s | Resultados | README §10.7 y §10.10 |
| 50 intentos a la misma silla: 1 con 201 y 49 con 409 | Resultados (Esteban) | README §10.12 |
| RR p95 3/3/4 ms frente a LC 3/2/2 ms | Alternativas, pregunta 1 | `carga-jj-20261114/informe.md` |
| 10 VU/s 100 % de flujos; 20 VU/s 39,17 % | Resultados (JJ), pregunta 7 | `cierre-verificado.md` |
| Workers: 503 de 47,53 / 61,35 / 60,49 %; CPU ≈ 1 núcleo en fase alta | Alternativas (Esteban), pregunta 6 | Registro §5.3.2 y §5.3.3 |

Si el informe o `ENTREGA\datos-medidos.md` cambian alguna cifra, gana `datos-medidos.md` y este guion se actualiza.

---

## 6. Índice tentativo de diapositivas (Ola 3, 13 diapositivas)

Archivo final: `docs/presentacion/presentacion-proyecto8.pptx`. En cada diapositiva, el nombre de quien la presenta en el pie.

| # | Título | Contenido | Presenta |
|:-:|---|---|---|
| 1 | Monitoreo de clúster HAProxy con Datadog | Título, curso, UAO, 6 integrantes con su rol (README "Integrantes") | Manuel |
| 2 | El problema: la Taquilla en venta flash | Qué pasa si se cae un servidor; qué necesita ver el equipo | Manuel |
| 3 | Requisitos del cliente | Partes 1 a 3 del PDF y P1 a P5, en una tabla requisito → dónde se cumple | Manuel |
| 4 | Restricciones y criterios | HAProxy 2.6 y Datadog impuestos; criterios de las matrices y cómo se mide cada uno | Juan José |
| 5 | Matriz: algoritmo de balanceo | RR frente a LeastConn, puntajes, sensibilidad, reflexión (captura 07) | Juan José |
| 6 | Matriz: workers de Gunicorn | 1, 2 y 4 workers (captura 08), límite de CPU | Esteban |
| 7 | Matrices: lectura del Agent y formato de logs | Socket Unix frente a HTTP y Prometheus; JSON frente a syslog | Jhon |
| 8 | Arquitectura | Fig. 1 (diagrama), recorrido de una petición | Manuel, Esteban, Jhon |
| 9 | Observabilidad en Datadog | Dashboard (captura 02), 3 monitores y sus umbrales | Alan |
| 10 | Demo | Video de 7 min (o enlace) y mapa P1 a P5 | Todos |
| 11 | Resultados: caída y errores | Tablas de README §10.10 (antes, durante y después; monitor de 5xx) | Sharon |
| 12 | Resultados: capacidad y concurrencia | 10 frente a 20 VU/s; misma silla 1/49; workers | Esteban, Juan José |
| 13 | Conclusiones y mejoras futuras | Qué cumple, qué quedó abierto (discrepancia 5xx, LeastConn), aporte de cada integrante | Sharon, Alan |
