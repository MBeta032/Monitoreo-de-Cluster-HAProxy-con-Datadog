# Guion del video de la demo · Proyecto 8

Duración: unos 21 minutos de grabación (máximo 23). Cubre P1 a P5 y dos ediciones de Artillery en vivo. Si al editar el video cortas las esperas del monitor, queda en unos 15 minutos.

Escenarios nuevos para el video (vienen con este guion):
- `demo-pico.yml`: tráfico normal, pico y regreso (5 min 30 s). Solo consulta la cartelera, así que no necesita usuario ni reiniciar sillas.
- `demo-errores.yml`: 4 minutos de tráfico con errores 401, 404 y 500 para disparar el monitor de 5xx.

---

## 1. Antes de grabar (no se graba, unos 15 min)

1. Copia los dos escenarios a la carpeta de Artillery del repo (PowerShell):
   ```powershell
   cd C:\proyectos\Monitoreo-de-Cluster-HAProxy-con-Datadog
   Copy-Item "C:\Users\manue\OneDrive - Universidad Autonoma de Occidente\SEPTIMO SEMESTRE\SERVICIOS TELEMATICOS\PROYECTO FINAL\ENTREGA\demo-pico.yml" artillery\
   Copy-Item "C:\Users\manue\OneDrive - Universidad Autonoma de Occidente\SEPTIMO SEMESTRE\SERVICIOS TELEMATICOS\PROYECTO FINAL\ENTREGA\demo-errores.yml" artillery\
   ```
2. Abre Docker Desktop y levanta todo:
   ```powershell
   docker compose up -d
   docker compose ps
   ```
   Debe verse `db`, `backend1`, `backend2` y `backend3` en `(healthy)`, y `haproxy` y `datadog-agent` arriba.
3. Revisa que el balanceador no haya quedado cambiado por pruebas anteriores:
   ```powershell
   git diff haproxy/haproxy.cfg
   ```
   No debe salir nada. Si sale algo: `git restore haproxy/haproxy.cfg` y `docker compose up -d --force-recreate haproxy`.

   ⚠️ **IP cruzadas en HAProxy:** `haproxy.cfg` no tiene `resolvers` y HAProxy solo resuelve las IP de los backends al arrancar. Si en alguna prueba anterior se detuvieron los 3 backends juntos, Docker pudo cambiarles la IP y las etiquetas de `backend1..3` quedan cruzadas en stats y en Datadog. Antes de grabar, con los 3 backends `(healthy)`, corre `docker compose restart haproxy`. Nunca reinicies HAProxy con un backend apagado. En P3 se detiene y arranca **un solo** backend (`backend2`), que conserva su IP. Detalle en `docs/pruebas/plan-de-pruebas.md` §5.
4. Prueba corta para confirmar que Artillery llega a Datadog (20 s):
   ```powershell
   docker compose --profile tools run --rm artillery run smoke-datadog.yml
   ```
   Debe terminar con 40 respuestas `200`.
5. En Datadog, confirma que los 3 monitores están en OK: Monitors → Manage. Si alguno sigue en alerta por una prueba anterior, espera a que vuelva a OK antes de grabar.
6. Abre las pestañas de Chrome en este orden:

   | # | Pestaña | Qué dejar listo |
   |:-:|---|---|
   | 1 | `http://localhost:8404/stats` | Página de estadísticas de HAProxy |
   | 2 | `https://app.datadoghq.com/dashboard/nne-fkp-w5z` | Rango **Past 15 Minutes** |
   | 3 | `https://app.datadoghq.com/event/explorer` | Búsqueda `Artillery` escrita |
   | 4 | `https://app.datadoghq.com/monitors/342430447` | Monitor de caída de backend |
   | 5 | `https://app.datadoghq.com/monitors/342430701` | Monitor de errores 5xx |
   | 6 | `https://app.datadoghq.com/logs` | Búsqueda `service:haproxy` escrita |

7. Abre VS Code con la carpeta del repo y deja abiertos `artillery/demo-pico.yml` y `artillery/demo-errores.yml`. Cierra cualquier pestaña con `.env`.
8. Deja dos ventanas de PowerShell en la carpeta del repo, con letra grande (Ctrl + rueda del mouse) y `Clear-Host`:
   - **T1**: para Artillery.
   - **T2**: para apagar y prender el backend.
9. Cierra WhatsApp, Teams y otras pestañas para liberar RAM. Activa "No molestar" en Windows.
10. Ten a mano la herramienta de recortes (Win + Shift + S) para las 4 capturas del informe. Guárdalas en `docs\evidencias\pruebas\05-entrega\capturas\` con los nombres de la sección 4.

**Nunca debe aparecer en pantalla:** el archivo `.env`, `docker compose config` sin `--quiet`, `docker inspect datadog-agent` ni tu bandeja de correo.

---

## 2. Guion minuto a minuto

Los minutos son del video. "+m:ss" es el tiempo desde que lanzas Artillery.

### Bloque A · El sistema arriba (P1) · 0:00 a 4:00

| Min | Qué hacer | Qué se ve | Qué decir |
|:-:|---|---|---|
| 0:00 | Presentarse | Tu pantalla con VS Code o el README | "Vamos a mostrar el clúster funcionando: HAProxy con tres backends, monitoreado con Datadog, y la carga generada con Artillery." |
| 0:30 | T1: `docker compose ps` | Los contenedores arriba | "Todo corre en Docker Compose: HAProxy, tres backends, PostgreSQL y el Agent de Datadog. En el equipo no hay nada más instalado." |
| 1:00 | T1: `curl.exe -s http://localhost:8080/api/info` y repetirlo 2 veces con la flecha arriba | `backend1`, `backend2`, `backend3` | "Cada petición llega al puerto 8080 y HAProxy la reparte por turnos: Round Robin." |
| 1:45 | Pestaña 1 (stats) | Los 3 backends en verde, `L7OK/200` | "HAProxy pregunta `/health` a cada backend cada segundo. Tres fallos seguidos lo sacan; dos aciertos lo devuelven." |
| 2:30 | Pestaña 2 (dashboard) y bajar por los grupos | Estado, tráfico, tiempo de espera, errores, saturación, reparto, base de datos | "Esto es el P1: el mismo estado en Datadog, con historial. El Agent lee el socket de HAProxy cada 5 segundos, los logs JSON y las métricas de cada backend." |
| 3:30 | **Captura 01** del dashboard completo | | |

### Bloque B · Edición 1 de Artillery y pico (P2) · 4:00 a 7:00

| Min | Qué hacer | Qué se ve | Qué decir |
|:-:|---|---|---|
| 4:00 | VS Code: `demo-pico.yml`. Mostrar las 5 fases | El archivo | "Este escenario simula un día de venta: 1 minuto normal, subida, pico, bajada y regreso. Cada usuario consulta la cartelera." |
| 4:20 | **Editar:** en la fase `pico` cambiar `arrivalRate: 15` por `25`, y en `subida` y `bajada` cambiar el `15` por `25`. Guardar (Ctrl + S) | El cambio | "Subimos el pico de 15 a 25 usuarios nuevos por segundo. No hay que reiniciar nada: la carpeta de Artillery está montada en el contenedor." |
| 4:45 | T1: `docker compose --profile tools run --rm artillery run demo-pico.yml` | Artillery arranca: `Phase started: antes` | "Artillery corre en su propio contenedor y le manda sus métricas al Agent por DogStatsD, con la etiqueta `test:demo-pico`." |
| 5:30 | Pestaña 3 (eventos), buscar `Artillery demo-pico` | El evento de inicio | "Este evento marca en Datadog el momento exacto en que empezó la prueba." |
| 6:15 (+1:30) | Pestaña 2, grupos Tráfico y Tiempo de espera | La curva de peticiones sube | "Ahí empieza el pico: las peticiones por segundo de HAProxy suben al mismo tiempo que la carga de Artillery. Esa es la correlación que pide el P2." |
| 6:45 | **Captura 02**: tráfico y tiempo de espera durante el pico | | |

### Bloque C · Caída de un backend (P3) · 6:45 a 10:30

| Min | Qué hacer | Qué se ve | Qué decir |
|:-:|---|---|---|
| 6:50 (+2:05) | T2: `docker compose stop backend2` | `Stopped` | "En pleno pico apago `backend2`, como si se cayera ese servidor." |
| 7:05 | Pestaña 1 (stats) | `backend2` en rojo, `DOWN` | "HAProxy lo saca en unos 5 segundos. Nosotros lo medimos en 5 y 6 segundos." |
| 7:20 | Pestaña 2, grupos Estado y Reparto | `backend2` en rojo; su tráfico cae a 0 y los otros dos suben | "Su tráfico se va a los otros dos. En nuestra corrida medida el reparto pasó de 33/33/33 a 1/49/49 y el servicio no se cortó." |
| 7:50 | Pestaña 4 (monitor de caída), F5 | `Triggered` con `backend:backend2` | "El monitor necesita dos lecturas seguidas en rojo y la evaluación de Datadog: suena alrededor de 60 segundos después y avisa por correo al equipo." Si aún no sale, recarga cada 15 s mientras explicas eso. |
| 8:20 (+3:35) | T2: `docker compose start backend2` | `Started` | "Lo vuelvo a prender." |
| 8:35 | Pestaña 1 (stats) | `backend2` vuelve a verde | "Vuelve en 4 a 9 segundos, cuando pasa dos chequeos seguidos." |
| 9:00 | Pestaña 2, grupo Reparto | De nuevo en tercios | "El reparto vuelve a tercios sin tocar nada en HAProxy." |
| 10:15 (+5:30) | T1 | Artillery termina y muestra el resumen | "Al final Artillery resume todo: peticiones, códigos y percentiles de latencia." Señalar `http.codes.200` y si apareció algún `502`. |

### Bloque D · Edición 2 de Artillery y errores (P4) · 10:30 a 16:30

| Min | Qué hacer | Qué se ve | Qué decir |
|:-:|---|---|---|
| 10:30 | VS Code: `demo-errores.yml` | El archivo con sus escenarios y pesos | "Este escenario mezcla tráfico correcto con errores: clave incorrecta (401), evento inexistente (404) y la ruta `/error`, que responde 500." |
| 10:50 | **Editar:** en `error_500` cambiar `weight: 2` por `weight: 10`. Guardar | El cambio | "Con peso 2, solo un 2 % de las peticiones falla y el monitor apenas avisaría. Con peso 10 pasamos a cerca del 9 %, por encima del umbral de 5 %." |
| 11:10 | T1: `docker compose --profile tools run --rm artillery run demo-errores.yml` | Artillery arranca | "Corre 4 minutos a 8 usuarios por segundo." |
| 11:40 | Pestaña 2, grupo Errores | El % de 5xx sube y cruza la línea de 2 % y luego la de 5 % | "El dashboard colorea la tasa de error: amarillo desde 2 % y rojo desde 5 %." |
| 12:30 | Pestaña 6 (logs): buscar `service:haproxy @status_code:>=500` | Las líneas con 500 | "Cada petición deja una línea JSON en HAProxy y Datadog convierte cada campo en un atributo, sin reglas extra. Aquí filtramos solo los errores 5xx: esto es el P4." |
| 13:15 | Abrir una línea del log | Atributos `status_code`, `server`, `total_ms`, `path` | "Se ve qué backend la atendió, la ruta y cuánto tardó." |
| 13:40 | Cambiar la búsqueda a `service:haproxy @server:backend2` y poner el rango en Past 15 Minutes | El hueco de `backend2` mientras estuvo apagado | "Y aquí está el hueco de `backend2`: no recibió tráfico mientras estuvo caído." |
| 14:00 | **Captura 03**: Log Explorer con el filtro de 5xx y un log abierto | | |
| 14:15 (+3:05) | Pestaña 5 (monitor de 5xx), F5 | `Warn` y luego `Triggered` | "El monitor promedia 5 minutos: avisa al pasar de 2 % y alerta al pasar de 5 %. En nuestra medición fue a 1 min 46 s y 2 min 46 s." Si aún no sale `Triggered`, recarga cada 15 s. |
| 15:15 (+4:05) | T1 | Artillery termina | Señalar `http.codes.500` y los demás códigos. |

### Bloque E · Antes, durante y después (P5) · 15:30 a 19:30

| Min | Qué hacer | Qué se ve | Qué decir |
|:-:|---|---|---|
| 15:30 | Pestaña 2, rango **Past 30 Minutes** | Toda la sesión en una línea de tiempo | "Ahora vemos todo junto." |
| 16:00 | Señalar con el mouse las zonas en Tráfico, Reparto y Errores | Antes (tráfico bajo), pico, caída de `backend2`, regreso, errores, después | "Antes: tráfico normal y reparto en tercios. Durante: el pico, la caída y los errores. Después: todo vuelve a la normalidad, y los eventos de Artillery marcan dónde empezó y terminó cada prueba. Esto es el P5." |
| 17:00 | Pestaña 3 (eventos) | Inicio y fin de `demo-pico` y `demo-errores` | "Con estos eventos sabemos exactamente qué carga causó cada cambio en las gráficas." |
| 17:30 | **Captura 04**: el dashboard con Past 30 Minutes | | |
| 18:00 | Pestaña 4 (monitor de caída) | Historial: `Triggered` y `Recovered` | "La alerta de la caída se cerró sola cuando el backend volvió." |

### Bloque F · Cierre · 19:30 a 21:00

| Min | Qué hacer | Qué decir |
|:-:|---|---|
| 19:30 | Pestaña 2 | "Mostramos P1 a P5: el dashboard en tiempo real, un pico de Artillery visto en Datadog, la alerta al apagar un backend, la búsqueda en los logs y la comparación antes, durante y después." |
| 20:15 | | "Las cifras con repeticiones y las matrices de decisión están en el informe y en el README del repositorio." |
| 20:45 | Fin de la grabación | |

El monitor de 5xx vuelve a OK unos 5 a 6 minutos después de terminar los errores. No hace falta grabarlo.

---

## 3. Plan B por bloque

| Si pasa esto | Haz esto |
|---|---|
| Un contenedor no está `healthy` | `docker compose up -d`, espera 30 s y repite `docker compose ps`. Si no sube, corta y vuelve a empezar |
| Artillery dice que el nombre `artillery` ya está en uso | `docker rm -f artillery` y vuelve a lanzar |
| No aparece el evento de Artillery | Espera 1 minuto (Datadog tarda entre 15 s y 1 min) y busca solo `Artillery` |
| El monitor de caída no sale en 90 s | Sigue con el guion y muestra la captura de Sharon `docs\evidencias\pruebas\03-falla\capturas\correo-caida-backend.jpeg` |
| `backend2` no vuelve a verde en 20 s | `docker compose restart backend2`. No reinicies HAProxy con un backend apagado |
| El log de 5xx sale vacío | Cambia el rango a Past 15 Minutes y espera 30 s |
| Algo falla a mitad del video | `docker compose start backend2`, espera a que el monitor vuelva a OK (unos 2 min) y vuelve a grabar ese bloque. Los bloques se pueden grabar por separado y unir al editar |

---

## 4. Capturas para el informe

| Captura | Archivo | Va en el informe | Momento |
|---|---|---|---|
| 01 | `01-dashboard.png` | Fig. 4 (P1) | 3:30 |
| 02 | `02-pico.png` | Fig. 5 (P2) | 6:45 |
| 03 | `03-logs.png` | Fig. 7 (P4) | 14:00 |
| 04 | `04-timeline.png` | Fig. 8 (P5) | 17:30 |

Para ponerlas en el informe: en `informe-ieee-final.docx`, haz clic en el recuadro gris de la figura, bórralo (clic derecho → Eliminar tabla), y en ese lugar usa Insertar → Imágenes. Ajusta el ancho a 8,9 cm (clic derecho → Tamaño y posición). El pie de figura ya está escrito debajo.

---

## 5. Si cambia algún número en el video

El informe usa las cifras medidas antes por Sharon y Juan José, que tienen repeticiones. Si en el video el monitor tarda distinto o aparece algún 502, se dice tal cual en la narración; no hace falta cambiar el informe.
