# Pruebas de carga de Juan José

Este manual documenta el ejecutor, el analizador y la campaña del 14/11/2026.
Los escenarios existentes se conservan. El ejecutor copia el escenario seleccionado
y aplica fases mediante `--overrides`; no modifica `normal.yml` ni `pico.yml`.

## Requisitos y alcance

- Docker Compose, Bash (Git Bash en Windows) y Python 3.9 o posterior.
- HAProxy y los tres backends en ejecución. Datadog activo para correlacionar métricas.
- Artillery 2.0.34, perfil `tools`, directorio de trabajo `/scripts`, red `cluster-net`.
- Montajes `./artillery:/scripts:ro` y `./artillery/resultados:/results` con escritura en resultados.
- Destino de carga: `http://haproxy:8080`. El puerto 8404 corresponde a estadísticas.
- Un GET `/` por usuario virtual en el escenario normal actual. `--tasa` significa
  usuarios nuevos por segundo, no usuarios simultáneos. No se afirma que existan
  operaciones de login o reservas en esta aplicación.

Desde la raíz del proyecto:

```bash
bash -n artillery/ejecutar_pruebas.sh
docker compose --profile tools config --quiet
docker compose ps
bash artillery/ejecutar_pruebas.sh normal --tasa 1 --duracion 30 --solo-validar
```

`--solo-validar` verifica parámetros y muestra las fases; no comprueba Compose ni
ejecuta Docker. El ejecutor normal comprueba configuración y servicios iniciados,
pero no certifica salud ni configuración efectiva de los procesos.

## Ejecutar una prueba

```bash
bash artillery/ejecutar_pruebas.sh normal --tasa 20 --duracion 300 --patron constante
python artillery/analizar_artillery.py artillery/resultados
```

Ejecutar una carga a la vez, sin modificar backends, Gunicorn ni Datadog durante
la comparación. Antes de cada tanda comprobar los tres servidores UP en
`http://localhost:8404/stats`. Conservar la evidencia de esa comprobación.

| Parámetro | Uso |
| --- | --- |
| `normal` o `pico` | YAML base del que se copia el flujo |
| `--tasa` | VU/s de la fase constante o máximo del patrón |
| `--duracion` | Duración total de fases en segundos, mínimo 30 |
| `--patron` | `constante`, `gradual`, `escalonado` o `pico` |
| `--base` | Tasa baja; por defecto `max(1, tasa // 5)` |
| `--solo-validar` | Solo muestra el plan |

Ejemplos de condiciones de la campaña (no es necesario repetirlas para generar el informe):

```bash
bash artillery/ejecutar_pruebas.sh normal --tasa 60 --duracion 300 --patron constante
bash artillery/ejecutar_pruebas.sh normal --tasa 20 --base 4 --duracion 300 --patron escalonado
bash artillery/ejecutar_pruebas.sh normal --tasa 20 --base 4 --duracion 300 --patron pico
bash artillery/ejecutar_pruebas.sh normal --tasa 20 --duracion 600 --patron constante
bash artillery/ejecutar_pruebas.sh normal --tasa 20 --duracion 900 --patron constante
```

En los patrones variables el máximo es 20 VU/s, pero la carga media es menor
que en la condición constante; sus totales no deben coincidir.

## Resultados y trazabilidad

Cada ejecución genera un ID con escenario, patrón, tasa, duración, UTC y sufijo
aleatorio. `artillery/resultados/ID.json` contiene el resultado de Artillery.
`artillery/corridas/ID/` contiene:

- `escenario.yml`: copia del flujo original.
- `overrides.json`: fases efectivamente solicitadas a Artillery.
- `inicio.json`: parámetros, comando, inicio y hashes de configuración local.
- `consola.log`: salida completa de la herramienta.
- `fin.json`: fin, código de salida y estado del proceso.

El estado `proceso_completado` no garantiza ausencia de respuestas HTTP de error;
se deben revisar los códigos y usuarios fallidos con el analizador. Una interrupción
conserva evidencia parcial y el ejecutor intenta detener únicamente su contenedor
de carga. No elimina resultados anteriores.

El analizador crea CSV separados por punto y coma, UTF-8 con BOM, con nombres
únicos. Incluye solicitudes/respuestas, tasas, TTFB medio/p50/p95/p99, códigos
1xx–5xx y usuarios creados/completados/fallidos. Los campos ausentes quedan vacíos.
No suma contadores duplicados por endpoint ni promedia percentiles de intervalos.

`rps_media_ventana` usa la ventana entre `firstMetricAt` y `lastMetricAt`;
se conserva separada de `rps_reportado_artillery`. El aviso de discrepancia de
más del 10 % exige revisar la definición y los intervalos, no descartar automáticamente
una corrida. TTFB no equivale a duración de sesión ni tiempo de descarga completa.

## Comparación de algoritmos

Se seleccionaron tres corridas consecutivas por algoritmo, a 20 VU/s y 300 s.
La identificación exacta de archivos y hashes está en
[la evidencia de campaña](evidencias/carga-jj-20261114/trazabilidad.json).
Se conservó igual el plan de carga y las huellas de escenario, Compose y Gunicorn.

El cambio temporal se limita a `balance roundrobin` / `balance leastconn`
dentro de `backend be_app`, coordinado con el responsable de HAProxy. Guardar el
archivo y revisar `git diff -- haproxy/haproxy.cfg`.

Validación desde Git Bash, antes de aplicar el cambio:

```bash
MSYS_NO_PATHCONV=1 docker compose run --rm --no-deps haproxy haproxy -c -f /usr/local/etc/haproxy/haproxy.cfg
```

Solo si la validación termina correctamente:

```bash
docker compose up -d --no-deps --force-recreate haproxy
```

Esperar a que los tres backends aparezcan UP. Esta recreación produce una
interrupción breve y reinicia contadores de HAProxy; no incluir ese intervalo como
una corrida de carga. Al terminar, restaurar `balance roundrobin`, validar y
aplicar de nuevo; verificar que el diff del archivo quede vacío.

## Informe de la campaña

[Informe con resultados y límites](evidencias/carga-jj-20261114/informe.md)

La carpeta incluye CSV de 14 corridas únicas, figuras PNG/SVG y trazabilidad SHA-256.
Las pruebas de humo y resultados antiguos se conservan fuera de esa selección.
La comparación base de 20 VU/s durante 5 minutos se reutiliza en tres grupos;
no son tres ejecuciones independientes.

Para regenerar las figuras se requiere Matplotlib. Puede instalarse en un entorno
virtual independiente; no se requiere para el ejecutor ni para el analizador:

```bash
python -m venv .venv-informe-jj
./.venv-informe-jj/Scripts/python.exe -m pip install -r artillery/requirements-informe-jj.txt
./.venv-informe-jj/Scripts/python.exe artillery/generar_informe_jj.py --repo . --salida docs/evidencias/carga-jj-regenerada
```

En Linux/macOS usar `.venv-informe-jj/bin/python`. La carpeta de salida debe ser
nueva. El generador es específico de esta campaña: valida la selección de IDs,
metadatos y condiciones; no identifica otras corridas como réplicas automáticamente.

## Evidencia de Datadog pendiente

El informe indica las ventanas de las seis corridas comparativas en UTC−05:00.
Para cada una conservar capturas o exportaciones con fecha, zona horaria, unidades
y filtros visibles: tasa de solicitudes, errores, latencia, CPU, memoria y estado
de cada backend. No interpretar TTFB de Artillery y `total_ms` de HAProxy como
la misma medida. No se han incorporado capturas de Datadog a este paquete.

El README registra una limitación pendiente de OpenMetrics con dos workers
de Gunicorn. Verificar la exactitud de los contadores con el responsable de backends
antes de usarlos como total de peticiones; no modificar Gunicorn dentro de esta
comparación. Referencia: [Prometheus multiproceso](https://prometheus.github.io/client_python/multiprocess/).

## Integración en Git

Revisar `git status --short`, `git diff --check` y el diff de Compose. Incluir archivos
de JJ y evidencias seleccionadas mediante rutas explícitas, no `git add .`.
Excluir `.env`, respaldos `*.bak`, `docker-compose-editor-respaldo.txt`, entornos
virtuales, cachés y resultados redundantes no seleccionados para el informe.
Mantener las evidencias originales existentes; no borrarlas al preparar el commit.

La sección 9 del README puede enlazar este manual sin modificar las secciones
de los otros integrantes.
