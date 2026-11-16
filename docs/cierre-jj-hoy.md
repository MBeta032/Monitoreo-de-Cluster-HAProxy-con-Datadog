# Cierre de pruebas de carga de Juan José

## Alcance y estado real

Esta copia está en la rama `feature/mejora-carga`, basada en `feature/mejora-dashboard`, commit `4358a09853a8d67f089897aef47579fd0041d742`. Esa base ya incorpora el backend mejorado con PostgreSQL y el dashboard. No hace falta reconstruirlos.

El desarrollo de JJ incluye Artillery en Compose, escenarios autenticados, reserva funcional con sesión/CSRF, ejecutor parametrizable, resultados identificados, análisis, CSV y gráficas. Las pruebas automatizadas de Python y JavaScript usan Docker/respuestas simulados: no sustituyen la ejecución real descrita aquí. No se han ejecutado desde el asistente las nuevas cargas contra Docker.

Las pruebas anteriores del backend simple se conservan como históricas. No prueban el rendimiento de la nueva taquilla. La campaña nueva mide consultas autenticadas; las mezclas de operaciones, pausas, contención de reservas y variaciones de workers se coordinan con Gargamel. No se presentan como medidas por esta campaña.

## Ejecución directa con Docker, sin Python en el host

El wrapper `ejecutar_pruebas.sh` y la campaña automatizada requieren Python 3 en el host. Artillery ejecutado directamente utiliza el runtime de su imagen y no requiere Python en el host.

Desde la raíz de un clon limpio, copia `.env.example` a `.env` sin sobrescribir un archivo existente. Completa las variables de infraestructura siguiendo el README (incluida una SECRET_KEY aleatoria y las contraseñas de la instalación), además de:

- `JJ_EMAIL`: correo de una cuenta demo del README, sección 6.
- `JJ_PASSWORD`: contraseña de esa cuenta demo, guardada solo en `.env`.
- `JJ_EVENT_ID`: ID del evento que se consultará; el seed inicial incluye el evento 1.

El bloque `environment` de Artillery transmite explícitamente esas variables. No se monta el archivo .env completo dentro del contenedor.

```bash
cp -n .env.example .env
# Editar .env y completar los valores antes de continuar.
docker compose --profile tools config --quiet
docker compose up -d --build db backend1 backend2 backend3 haproxy datadog-agent
# Esperar a que los tres backends aparezcan UP en http://localhost:8404/stats.
mkdir -p artillery/resultados
docker compose run --rm artillery run /scripts/pico.yml -o /results/pico.json
```

El último comando ejecuta el perfil gradual de `pico.yml` (540 segundos de fases), con consultas autenticadas. No crea reservas ni cambia el algoritmo de HAProxy. No equivale a la campaña de 14 corridas. Revisa los códigos HTTP y `vusers.failed` del resultado; terminar el proceso no garantiza que todas las solicitudes fueran exitosas.

Para evitar reemplazar un resultado previo, usa un nombre único en Git Bash:

```bash
docker compose run --rm artillery run /scripts/pico.yml -o "/results/pico-$(date -u +%Y%m%dT%H%M%S)-${RANDOM}.json"
```

El resultado aparece en `artillery/resultados/` gracias al volumen `/results`. En Git Bash, si MSYS convierte las rutas `/scripts` o `/results` en rutas de Windows, antepone `MSYS_NO_PATHCONV=1` al comando. El ejecutor Python evita esa conversión al invocar Docker directamente.

## Alcance de la restauración de HAProxy

La campaña modifica temporalmente el archivo real `haproxy/haproxy.cfg` de esta copia, montado por Compose. No utiliza una copia alternativa montada: guarda el original en la carpeta de la campaña, aplica el algoritmo y recrea solo HAProxy.

El bloque `finally` intenta restaurar los bytes originales y validar/recrear el servicio al finalizar, ante excepciones y ante un Ctrl+C que llegue a Python como KeyboardInterrupt. No garantiza recuperación automática ante un corte de energía, cierre forzado del proceso o una segunda interrupción durante la restauración. Si Docker no responde, puede quedar restaurado el archivo pero pendiente la recreación del servicio. Revisa `restauracion_haproxy` en el manifiesto y aplica la recuperación manual de esta guía cuando sea necesario. No ejecutes campañas simultáneas ni edites HAProxy durante una campaña.

## 1. Abrir la copia preparada

Abre Docker Desktop y usa Git Bash:

```bash
cd ~/Documents/integracion
git branch --show-current
python -m venv .venv-jj
source .venv-jj/Scripts/activate
python -m pip install -r artillery/requirements-informe-jj.txt
```

La rama esperada es `feature/mejora-carga`. Si ya creaste el entorno, basta activarlo. Conserva abierta esta terminal. La carpeta original de Proyecto permanece separada; el despliegue usa los mismos nombres de proyecto/contenedores y actualizará el laboratorio local existente.

## 2. Preparar y levantar

```bash
python artillery/cierre_hoy.py preparar --env-origen "C:/Users/ADMIN/Desktop/Universidad/Septimo Semestre/Telematicos/Proyecto/.env"
docker compose --profile tools config --quiet
docker compose up -d --build db backend1 backend2 backend3 haproxy datadog-agent
docker compose ps
```

`preparar` copia el .env solo si falta, conserva sus valores y completa las variables locales de prueba usando las cuentas demo del README. No imprime contraseñas. Con una base nueva genera claves de PostgreSQL; si ya existe `pg-data` y faltan claves, debes colocar las claves reales de esa instalación en el .env de esta copia. No borres el volumen ni uses `down -v` para solucionarlo. Comprueba también `DD_API_KEY` y `DD_SITE` en tu editor sin publicarlas.

Continúa solo si los comandos terminan correctamente. Si un servicio falla:

```bash
docker compose ps -a
docker compose logs --tail 50 db backend1 backend2 backend3 haproxy
```

## 3. Validación funcional obligatoria

```bash
python artillery/cierre_hoy.py humo --con-reserva
```

Debe terminar con `HUMO CORRECTO`. Ejecuta dos flujos de un usuario: consulta autenticada y reserva. Crea una reserva real, verifica CSRF y comprueba que aparece en Mis reservas. Si falla, corrige el problema antes de iniciar la campaña larga. Un 401/403 indica autenticación/CSRF; falta de cupos requiere elegir en .env otro `JJ_EVENT_ID` con sillas disponibles y repetir humo. No elimines reservas para esconder fallos.

## 4. Ejecutar una sola campaña

```bash
python artillery/cierre_hoy.py campana --base 2
```

Son 14 corridas y **85 minutos de fases**, más arranque, cierre y espera de usuarios. Mantén el equipo despierto y evita otras cargas simultáneas. El script cambia únicamente el algoritmo de HAProxy durante la comparación y restaura la configuración original al finalizar o ante una interrupción controlada.

| Criterio | Configuración |
|---|---|
| Intensidad | 10, 20, 40 y 60 VU/s; 5 minutos cada una |
| Patrón | Constante, escalonado y pico; máximo 10 VU/s, base variable 2 |
| Duración | 5, 10 y 15 minutos a 2 VU/s |
| Algoritmo | Round Robin y LeastConn; tres repeticiones de 5 minutos a 2 VU/s |

La corrida constante de intensidad 10 sirve de referencia de patrones; la primera Round Robin de 5 minutos sirve también de referencia de duración. Por ello no se duplican pruebas. Los patrones variables generan menos volumen que el constante.

Cada VU inicia sesión y consulta cartelera, sillas y reservas: cuatro solicitudes si completa el flujo. **VU/s no equivale a solicitudes/s ni a usuarios concurrentes**. Esta campaña no realiza reservas masivas. El inicio de sesión puede dominar el coste; se conserva como parte explícita del perfil.

Si se interrumpe, usa el comando con ID que imprime el ejecutor, por ejemplo:

```bash
python artillery/cierre_hoy.py campana --reanudar ID_DE_LA_CAMPANA
```

Sustituye el marcador por el ID real `taquilla-...`. Omite las corridas ya completadas válidamente. No cambies código/workers entre corridas; si los cambias, debes validar humo y hacer una campaña nueva.

Ante un cierre abrupto del equipo que impida restaurar HAProxy, copia `artillery/campanas/ID_DE_LA_CAMPANA/haproxy-original.cfg` a `haproxy/haproxy.cfg`, y ejecuta:

```bash
docker compose run --rm --no-deps haproxy haproxy -c -f /usr/local/etc/haproxy/haproxy.cfg
docker compose up -d --no-deps --force-recreate haproxy
```

Después reanuda. No interpretes las corridas faltantes como ceros.

## 5. Evidencias y conclusiones

El informe se genera automáticamente al terminar, también para una campaña parcial con corridas completadas. La terminal muestra `INFORME:` y su carpeta. Para regenerarlo sin repetir carga:

```bash
python artillery/cierre_hoy.py informe --ultima
```

| Contenido | Ubicación |
|---|---|
| Escenarios, procesador y ejecutores | `artillery/` |
| JSON originales nuevos | `artillery/resultados/taquilla/ID/` |
| Plan, consola, tiempos, imágenes y configuración montada | `artillery/campanas/ID/` |
| CSV, gráfica PNG e informe Markdown | `docs/evidencias/ID/FECHA/` |
| Resultados del backend anterior | JSON anteriores en `artillery/resultados/`, `artillery/corridas/` y `docs/evidencias/carga-jj-20261114/` |
| Implementación y procedimiento anteriores | Historial de Git y `docs/historico-jj/` |

Lee el estado del manifiesto: `completada` indica que se ejecutó el plan, no que todas las solicitudes tuvieron éxito. Revisa 4xx, 5xx, usuarios fallidos, flujos completos, percentiles y restauración de HAProxy. Los 401/403 detienen la campaña porque invalidan la autenticación. Los fallos bajo carga se conservan como resultados.

Usa el [dashboard existente](https://app.datadoghq.com/dashboard/nne-fkp-w5z), o su [vista pública documentada](https://p.datadoghq.com/sb/95a7b1a2-d9f8-11f1-b57e-baea63f7b3d6-ccacbd422eed735a402e91352d62c6ba). Selecciona las ventanas UTC de `informe.md` (Colombia es UTC−5). Guarda capturas con rango horario visible de tráfico/latencia, CPU/memoria, reparto entre backends y errores. Colócalas junto al informe y reemplaza su nota de capturas pendientes por enlaces y observaciones reales. No captures credenciales.

El dashboard ya existe; lo pendiente de JJ es correlacionar sus propias corridas. Las alertas y caídas se coordinan con sus responsables; no se afirman probadas por haber ejecutado carga. Si no aparecen métricas, revisa con Jhon `docker compose exec -T datadog-agent agent status` y no declares validada esa correlación.

No declares un ganador universal entre algoritmos por diferencias de pocos milisegundos. No promedies p95 para presentarlo como un percentil global. Si no aparece un punto de quiebre, documenta «no observado en el rango ensayado»; si hay fallos, correlaciona recursos, colas y latencia antes de atribuirlos a saturación. No hace falta repetir toda la campaña histórica.

## 6. Revisar, guardar y entregar

```bash
git diff --check
git diff -- docker-compose.yml haproxy/haproxy.cfg
git status --short
git add -- .gitignore docker-compose.yml README.md artillery docs/cierre-jj-hoy.md docs/historico-jj docs/evidencias
git diff --cached --check
git diff --cached --stat
git diff --cached --name-only
```

Revisa que los cambios sean los esperados, que HAProxy haya quedado como estaba y que no aparezcan .env, claves, el entorno virtual o respaldos ajenos. Las carpetas añadidas deben contener solo las evidencias y archivos previstos. Después:

```bash
git commit -m "feat(carga): integrar pruebas de taquilla y evidencias de JJ"
git push -u origin feature/mejora-carga
```

Abre el PR desde `feature/mejora-carga` hacia `develop`, como solicitó el equipo. Revisa Files changed y los commits: esta rama parte de las mejoras de backend/dashboard y puede incluirlas si develop todavía no las contiene. No fusiones automáticamente cambios ajenos ni resuelvas sus conflictos sin revisar el contenido con los responsables.

El PR debe indicar perfil de tráfico, campaña/fechas, resultados y limitaciones; enlazar informe y capturas; distinguir pruebas automatizadas de ejecución real. La entrega queda completa cuando los criterios acordados están ejecutados, el análisis está respaldado por JSON reales, la evidencia de Datadog está correlacionada y el PR contiene los archivos. Un fallo de rendimiento también es un resultado válido si se analiza y documenta.
