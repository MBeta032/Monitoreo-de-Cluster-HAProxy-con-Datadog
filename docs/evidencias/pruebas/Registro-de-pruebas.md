# Registro de pruebas

## 1. Objetivo

Documentar las pruebas realizadas sobre el clúster HAProxy y su integración con Datadog, registrando las configuraciones utilizadas, los resultados obtenidos y las evidencias correspondientes.

Este registro permite hacer seguimiento al comportamiento de la infraestructura, verificar la recepción de métricas y eventos en Datadog y analizar la respuesta del sistema ante diferentes condiciones de carga y disponibilidad.

## 2. Integración Artillery–Datadog

### 2.1. Prueba de integración (Smoke Test)

**Archivo ejecutado:** `artillery/smoke-datadog.yml`

**Objetivo:** Verificar la comunicación entre Artillery y Datadog mediante DogStatsD, comprobando el envío de métricas y eventos.

**Resultados:**

| Indicador | Resultado |
|---|---:|
| Duración | 20 segundos |
| Solicitudes | 40 |
| Respuestas exitosas (200) | 40 |
| Solicitudes fallidas | 0 |
| Tiempo medio de respuesta | 16.4 ms |
| Mediana | 3 ms |
| Percentil 95 | 10.1 ms |
| Percentil 99 | 10.1 ms |

**Verificación en Datadog:**

- Se confirmó la recepción de `artillery.http.requests` con la etiqueta `test:smoke-datadog`.
- Se visualizaron los eventos de inicio y finalización de la prueba.
- Se comprobó que las métricas enviadas coinciden con los resultados de Artillery.

**Conclusión:** La integración entre Artillery y Datadog mediante DogStatsD funcionó correctamente. Se recibieron las métricas y los eventos generados durante la ejecución.

**Evidencias:** `evidencias/01-integracion-datadog/capturas/`

## 3. Prueba de errores controlados

### 3.1. Escenario ejecutado

**Archivo:** `artillery/errores.yml` · **Etiqueta en Datadog:** `test:errores`

**Objetivo:** comprobar cómo responde el sistema ante errores controlados y verificar que el monitor de errores 5xx se activa y se recupera.

La prueba dura 7 minutos (420 s) con 5 usuarios virtuales nuevos por segundo. Cada usuario virtual ejecuta un escenario elegido al azar según su peso:

| Escenario | Peso | Qué hace | Respuesta esperada |
|---|---:|---|:---:|
| `cartelera` | 40 % | `GET /api/events` | 200 |
| `detalle_evento` | 30 % | `GET /api/events/1` | 200 |
| `error_500` | 10 % | `GET /error` | 500 |
| `login_incorrecto_401` | 5 % | `POST /api/login` con contraseña incorrecta | 401 |
| `reserva_sin_csrf_403` | 5 % | Inicia sesión y reserva sin `X-CSRF-Token` | 200 y 403 |
| `silla_inexistente_404` | 5 % | Inicia sesión y reserva la silla 999999 | 200 y 404 |
| `evento_inexistente_404` | 5 % | `GET /api/events/999999` | 404 |

El escenario no reserva ninguna silla, así que no hace falta reiniciar los datos entre corridas. Las peticiones llevan un nombre fijo y el plugin `metrics-by-endpoint` se configuró con `useOnlyRequestNames: true`, para que Datadog reciba una métrica por tipo de petición y no una por URL.

### 3.2. Resultados de Artillery (corrida A)

| Indicador | Resultado |
|---|---:|
| Duración | 7 minutos |
| Solicitudes totales | 2.293 (≈ 5,5 por segundo) |
| Usuarios virtuales creados · completados · fallidos | 2.100 · 2.100 · 0 |

**Respuestas HTTP:**

| Código | Cantidad | Porcentaje | Interpretación |
|---|---:|---:|---|
| 200 | 1.678 | 73,2 % | Solicitudes exitosas |
| 401 | 113 | 4,9 % | Credenciales incorrectas |
| 403 | 110 | 4,8 % | Reserva sin token CSRF |
| 404 | 179 | 7,8 % | 96 eventos inexistentes y 83 sillas inexistentes |
| 500 | 213 | 9,3 % | Error interno forzado (`/error`) |
| **Total** | **2.293** | **100 %** | |

Los 213 errores 500 son el 10,1 % de los 2.100 usuarios virtuales y el 9,3 % de las peticiones: corresponde al 10 % de tráfico al endpoint de error que pide el diseño.

**Latencia global:** media 60,7 ms · mediana 4 ms · p95 376,2 ms · p99 620,3 ms · máximo 1.535 ms.

**Latencia por tipo de petición (ms):**

| Petición | Cantidad | Mediana | p95 | p99 |
|---|---:|---:|---:|---:|
| `cartelera` | 841 | 4 | 10,9 | 21,1 |
| `evento` | 644 | 4 | 8,9 | 45,2 |
| `error_500` | 213 | 2 | 5 | 13,1 |
| `evento_404` | 96 | 4 | 10,9 | 19,1 |
| `silla_404` | 83 | 7 | 19,1 | 51,9 |
| `reserva_403` | 110 | 4 | 7 | 10,1 |
| `login_ok` | 193 | 347,3 | 727,9 | 1.249,1 |
| `login_401` | 113 | 354,3 | 584,2 | 757,6 |

**Lectura.** Los inicios de sesión son el 13,3 % de las peticiones y tienen una mediana de unos 350 ms; todo lo demás tiene una mediana de entre 2 y 7 ms. Ese costo es el hash de contraseña (unos 300 ms de CPU por inicio de sesión, ver sección 6.7). Por eso el p95 global (376 ms) describe casi solo al inicio de sesión y no a las consultas, y por eso las respuestas 4xx tienen una media alta (116 ms): no por fallar, sino porque entre ellas está el 401, que paga el hash. Los errores 500 forzados son las respuestas más baratas (mediana de 2 ms): un error interno de este tipo no consume capacidad.

### 3.3. Repetición y verificación en Datadog (corrida B)

La prueba se ejecutó dos veces. La distribución de códigos es parecida y el porcentaje de 5xx se mantiene, que es lo que se espera de un reparto aleatorio con pesos fijos:

| Corrida | Solicitudes | 200 | 401 | 403 | 404 | 500 | % de 5xx |
|---|---:|---:|---:|---:|---:|---:|---:|
| A | 2.293 | 1.678 | 113 | 110 | 179 | 213 | 9,3 % |
| B | 2.299 | 1.663 | 105 | 109 | 211 | 211 | 9,2 % |

En la corrida B se comprobó que Datadog recibió las métricas con la etiqueta `test:errores` y que coinciden con el reporte de Artillery:

| Métrica en Datadog | Datadog | Artillery |
|---|---:|---:|
| `artillery.http.requests` | 2,30 k | 2.299 |
| `artillery.http.codes.200` | 1,66 k | 1.663 |
| `artillery.http.codes.401` | 105 | 105 |
| `artillery.http.codes.403` | 109 | 109 |
| `artillery.http.codes.404` | 211 | 211 |
| `artillery.http.codes.500` | 211 | 211 |

También se visualizaron en Event Explorer los eventos de inicio y de fin de la prueba.

### 3.4. Verificación del monitor de errores 5xx (corrida A)

El monitor `[HAProxy] Tasa elevada de errores HTTP 5xx` avisa cuando el promedio de 5 minutos supera el 2 % y alerta cuando supera el 5 %. Los tres correos llegaron al canal del equipo (`@team-haproxy-telematicos`):

| Momento | Hora del correo (Cali) | UTC | Tiempo desde el inicio o el fin |
|---|:---:|:---:|---|
| Inicio de la corrida | ≈ 12:39 | ≈ 17:39 | |
| `[AVISO]` > 2 % | 12:42 | 17:42 | ≈ 2 a 3 min tras el inicio |
| `[ALERTA]` > 5 % | 12:43 | 17:43 | ≈ 3 a 4 min tras el inicio |
| Fin de la corrida | ≈ 12:46 | 17:46 | |
| `[RECUPERADO]` | 12:53 | 17:53 | ≈ 6 a 7 min tras el fin |

Los tiempos concuerdan con lo esperado (sección 8.3): el promedio de 5 minutos y los 60 s de espera hacen que la alerta tarde unos minutos, y la recuperación llega cuando los errores salen de la ventana de 5 minutos. Los tiempos son aproximados porque los correos tienen resolución de un minuto.

### 3.5. Conclusiones de la prueba

- El sistema respondió a todas las situaciones de error con el código HTTP esperado (401, 403, 404 y 500), sin usuarios virtuales fallidos.
- El monitor de 5xx se activó (aviso y alerta) y se recuperó, y la notificación llegó por correo.
- El costo del inicio de sesión domina la cola de latencia, por lo que conviene analizar los percentiles por tipo de petición y no solo el global.

**Evidencias:** `evidencias/02-errores/capturas/`

## 4. Prueba de caída y recuperación de un backend

### 4.1. Escenario ejecutado

**Archivos:** `artillery/falla.yml` (carga) y `artillery/falla.sh` (coordinación) · **Etiqueta en Datadog:** `test:falla`

**Objetivo:** comprobar si HAProxy sigue repartiendo las peticiones entre los backends disponibles cuando uno se cae, y si Datadog detecta la caída y la recuperación.

Artillery solo genera la carga; el script controla los contenedores con Docker Compose. La carga es de solo lectura (`GET /api/events`), sin inicio de sesión, para que el costo del hash de contraseñas no tape el efecto de la caída. Dura 6 minutos: un calentamiento de 30 s y una meseta constante. En el minuto 2 se detiene un backend (`docker compose stop`) y en el minuto 4 se vuelve a iniciar. Se hicieron dos corridas con backends y cargas distintos.

### 4.2. Línea de tiempo medida

| Evento | Corrida 1 (20 req/s, `backend1`) | Corrida 2 (30 req/s, `backend2`) |
|---|:---:|:---:|
| Orden de detener (UTC) | 20:14:07 | 21:06:28 |
| HAProxy lo marca DOWN | 5 s | 6 s |
| Correo de caída (hora de Cali) | 15:15 | 16:07 |
| Orden de iniciar (UTC) | 20:16:07 | 21:08:28 |
| HAProxy lo marca UP | 4 s | 9 s |
| Correo de recuperación (hora de Cali) | 15:17 | 16:08 |

La caída se detectó en 5 a 6 s, lo que coincide con el health check de HAProxy (`inter 1s`, `fall 3`). La recuperación tardó entre 4 y 9 s, porque el backend debe arrancar Gunicorn y pasar dos chequeos de salud (`rise 2`). El correo de caída llegó entre 0,5 y 2 minutos después de la orden: dos lecturas seguidas del Agent (cada 5 s) más la evaluación del monitor de Datadog. Las horas de los correos tienen resolución de un minuto.

### 4.3. Reparto de las peticiones

Sesiones atendidas por cada backend en una ventana de unos 10 s (según las estadísticas de HAProxy):

| Momento | Corrida 1 (b1 / b2 / b3) | Corrida 2 (b1 / b2 / b3) |
|---|:---:|:---:|
| Con el backend caído | 0 / 104 / 104 | 158 / 0 / 156 |
| Después de la recuperación | 68 / 67 / 67 | 101 / 101 / 100 |

Con un backend caído, los otros dos se reparten la carga en partes iguales, y al volver el tráfico se reparte de nuevo en tercios. El servicio no se interrumpió.

### 4.4. Resultados de Artillery

| Indicador | Corrida 1 | Corrida 2 |
|---|---:|---:|
| Peticiones | 6.975 | 10.425 |
| Respuestas 200 | 6.974 (99,986 %) | 10.424 (99,990 %) |
| Respuestas 502 | 1 (0,014 %) | 1 (0,010 %) |
| Usuarios virtuales fallidos | 0 | 0 |
| Latencia: mediana · p95 · p99 (ms) | 4 · 8,9 · 16 | 5 · 27,9 · 135,7 |
| Latencia máxima (ms) | 2.011 | 2.008 |

En cada corrida una sola petición recibió un 502, y el máximo de latencia fue de unos 2 s, coherente con el `timeout connect` de 2 s de HAProxy y la redistribución a otro backend. Esto afecta a las peticiones que estaban en curso o asignadas al backend caído antes de que HAProxy lo marcara DOWN. Al subir de 20 a 30 peticiones por segundo, el p99 pasó de 16 a 135,7 ms. Parte de ese aumento puede corresponder al generador de carga (la sesión más larga fue de 6,4 s con una respuesta máxima de 2,0 s), por lo que la latencia que ve HAProxy en los logs es la referencia para el clúster.

### 4.5. Conclusiones de la prueba

- HAProxy detectó la caída en 5 a 6 s y la recuperación en 4 a 9 s, y repartió la carga entre los backends sanos sin interrumpir el servicio.
- Más del 99,98 % de las peticiones se respondió bien; por cada caída hubo un error 502 y algunas peticiones de hasta 2 s.
- Datadog detectó la caída y la recuperación y las notificó por correo.
- La medición de la sección 5.7 (backends temporales, 60 peticiones, 0 errores) se actualiza con estos datos, con backends reales y carga sostenida.

**Evidencias:** `docs/evidencias/pruebas/03-falla/capturas/`

## 5. Experimentos de rendimiento

### 5.1. Objetivo

EEvaluar el comportamiento del clúster HAProxy bajo diferentes condiciones de carga, con el propósito de identificar cómo influyen la proporción de operaciones de consulta y reserva, la cantidad de workers de Gunicorn, los tiempos de espera entre solicitudes y la concurrencia de las reservas en los tiempos de respuesta, el consumo de recursos, la disponibilidad de los servidores y la estabilidad general del sistema.

Se realizaron cuatro grupos de experimentos:

- Proporciones de consultas y reservas: se compararon tres escenarios (70/30, 50/50 y 30/70).
- Cantidad de workers de Gunicorn: se evaluaron configuraciones de uno, dos y cuatro workers por backend.
- Pausas entre solicitudes: se compararon usuarios virtuales sin pausas, con pausas aleatorias de uno a tres segundos y con pausas de cinco segundos.
- Concurrencia en las reservas: se evaluaron solicitudes simultáneas sobre una misma silla y sobre sillas diferentes.

Los resultados se analizaron mediante Artillery, para obtener las estadísticas de las solicitudes y los usuarios virtuales, y Datadog, para observar el comportamiento de HAProxy, los servidores backend, la base de datos y los eventos de monitoreo.

---

### 5.2. Experimentos con diferentes proporciones de consultas y reservas

#### 5.2.1. Configuración de los escenarios

Los tres escenarios utilizaron los siguientes flujos:

| Escenario | Operación | Solicitudes |
|---|---|---|
| Consulta de sillas | Consulta la disponibilidad del evento | `GET /api/events/1/seats` |
| Reserva de silla | Obtiene una silla disponible, inicia sesión y solicita la reserva | `POST /api/login` y solicitud de reserva de la silla |

Las proporciones se configuraron mediante los pesos de los escenarios de Artillery:

| Prueba | Consultas | Reservas | Duración | Usuarios virtuales esperados |
|---|---:|---:|---:|---:|
| 70/30 | 70 % | 30 % | 420 s | 2.100 |
| 50/50 | 50 % | 50 % | 420 s | 2.100 |
| 30/70 | 30 % | 70 % | 420 s | 2.100 |

Cada ejecución utilizó una etiqueta diferente en Datadog para facilitar la identificación de sus métricas:

- `test:proporcion_70_30`
- `test:proporcion_50_50`
- `test:proporcion_30_70`

El plugin `metrics-by-endpoint` se configuró con `useOnlyRequestNames: true` para diferenciar las consultas, los inicios de sesión y las reservas.

**Consideración sobre la medición:** durante el flujo de reserva, el procesador realiza una consulta adicional para obtener una silla disponible mediante `fetch`. Esta petición llega al clúster, pero no queda contabilizada dentro de las solicitudes HTTP de Artillery ni de sus métricas por endpoint. Por esta razón, las cifras de solicitudes registradas por Artillery no representan la totalidad de las peticiones recibidas por HAProxy.

#### 5.2.2. Resultados de Artillery

**Distribución de usuarios virtuales**

| Indicador | 70/30 | 50/50 | 30/70 |
|---|---:|---:|---:|
| Usuarios creados | 2.100 | 2.100 | 2.100 |
| Usuarios completados | 2.098 | 2.100 | 2.100 |
| Usuarios fallidos | 2 | 0 | 0 |
| Usuarios de consulta | 1.440 | 1.040 | 615 |
| Usuarios de reserva | 660 | 1.060 | 1.485 |
| Porcentaje real de consultas | 68,57 % | 49,52 % | 29,29 % |
| Porcentaje real de reservas | 31,43 % | 50,48 % | 70,71 % |

Las distribuciones reales se aproximaron a los pesos configurados en Artillery. Las dos sesiones fallidas de la prueba 70/30 correspondieron a errores `fetch failed` durante la consulta de disponibilidad realizada por el procesador de reservas.

**Respuestas HTTP**

| Indicador | 70/30 | 50/50 | 30/70 |
|---|---:|---:|---:|
| Solicitudes registradas por Artillery | 2.756 | 3.160 | 3.585 |
| Respuestas 200 | 2.098 | 2.100 | 2.100 |
| Respuestas 201 | 658 | 1.059 | 1.483 |
| Respuestas 409 | 0 | 1 | 2 |
| Reservas exitosas | 658 | 1.059 | 1.483 |
| Usuarios virtuales fallidos | 2 | 0 | 0 |

Las respuestas HTTP 201 representan reservas confirmadas. Los códigos 409 corresponden a conflictos de disponibilidad cuando una silla seleccionada ya había sido reservada.

En las pruebas 50/50 y 30/70 se presentaron uno y dos conflictos, respectivamente. A pesar de estos casos, todos los usuarios virtuales completaron sus escenarios.

**Latencia global**

| Indicador (ms) | 70/30 | 50/50 | 30/70 |
|---|---:|---:|---:|
| Tiempo mínimo | 5 | 5 | 5 |
| Tiempo máximo | 4.272 | 1.369 | 4.184 |
| Tiempo medio | 145,3 | 172,1 | 260,1 |
| Mediana | 15 | 13,1 | 16,9 |
| Percentil 95 (p95) | 645,6 | 658,6 | 788,5 |
| Percentil 99 (p99) | 1.153,1 | 889,1 | 1.826,6 |

**Latencia por tipo de petición**

| Operación | Indicador (ms) | 70/30 | 50/50 | 30/70 |
|---|---|---:|---:|---:|
| Consulta de sillas | Media | 29,9 | 15,7 | 17,3 |
| | p95 | 58,6 | 27,9 | 37,7 |
| | p99 | 391,6 | 73 | 87,4 |
| Inicio de sesión | Media | 502 | 480,5 | 605 |
| | p95 | 944 | 788,5 | 1.153,1 |
| | p99 | 1.755 | 1.085,9 | 2.566,3 |
| Reserva de silla | Media | 41,3 | 17,2 | 15,9 |
| | p95 | 29,1 | 36,2 | 48,9 |
| | p99 | 713,5 | 96,6 | 89,1 |

El inicio de sesión fue la operación con mayor tiempo de respuesta en las tres ejecuciones. Esto se relaciona con el procesamiento de las credenciales y el cálculo del hash de contraseña. Por tanto, el tiempo global de la prueba está influido considerablemente por la autenticación que forma parte del flujo de reserva.

Los percentiles de la reserva deben interpretarse teniendo en cuenta que la operación presentó pocos tiempos elevados frente a la mayoría de respuestas rápidas. Por esta razón, en algunos escenarios la media y los percentiles no siguen el mismo comportamiento.

#### 5.2.3. Resultados del monitoreo con Datadog

El monitoreo permitió observar el comportamiento de los tres servidores durante las pruebas:

- **Distribución de solicitudes:** HAProxy mantuvo un reparto prácticamente equilibrado entre los tres backends, cercano al 33,33 % para cada uno.
- **Errores y colas:** no se observaron errores HTTP 5xx en las métricas de HAProxy ni acumulación de solicitudes en las colas de los servidores durante estos escenarios.
- **Uso de CPU:** el consumo aumentó en el escenario 30/70, con promedios aproximados entre el 45 % y el 51 % por backend. Aun así, permaneció por debajo del límite de un núcleo asignado a cada contenedor.
- **Uso de memoria:** se mantuvo estable, con promedios inferiores a 110 MB, frente al límite de 384 MB por backend.
- **Base de datos:** las conexiones utilizadas se mantuvieron alrededor del 25 % del máximo configurado.

En conjunto, las métricas muestran que, para estas condiciones de carga, el clúster distribuyó las solicitudes de forma equilibrada y no presentó señales de saturación en los recursos monitoreados.

#### 5.2.4. Análisis comparativo

Al comparar las tres ejecuciones se observa que el tiempo medio global aumentó a medida que se incrementó la proporción de usuarios que realizaban reservas:

- En 70/30, el tiempo medio fue de 145,3 ms.
- En 50/50, aumentó a 172,1 ms.
- En 30/70, alcanzó 260,1 ms.

Entre las pruebas 50/50 y 30/70, el tiempo medio aumentó aproximadamente un 51 %. También se incrementó el p99, que pasó de 889,1 ms a 1.826,6 ms. Esto evidencia una mayor variabilidad en los tiempos de respuesta cuando predominan las operaciones de reserva.

La autenticación presentó el mayor incremento: su tiempo medio pasó de 480,5 ms en 50/50 a 605 ms en 30/70. Su p99 alcanzó 2.566,3 ms en la última ejecución, lo que muestra que algunos inicios de sesión tardaron considerablemente más que la mayoría.

El escenario 30/70 representó la mayor exigencia para el sistema en este grupo de experimentos, especialmente por el incremento en los tiempos de autenticación y el consumo de CPU. Sin embargo, los servidores conservaron su disponibilidad y no se registraron errores 5xx en las métricas de HAProxy durante estas ejecuciones.

---

### 5.3. Experimentos con diferentes cantidades de workers de Gunicorn

#### 5.3.1. Objetivo y configuración

El segundo grupo de experimentos buscó evaluar cómo influye la cantidad de workers de Gunicorn en la capacidad de procesamiento de cada backend, el consumo de CPU y memoria, los tiempos de respuesta y la disponibilidad del clúster.

Se realizaron tres ejecuciones, modificando la cantidad de workers por servidor backend:

| Prueba | Workers por backend | Procesos esperados por backend (incluido el master) |
|---|---:|---:|
| 1 worker | 1 | 2 |
| 2 workers | 2 | 3 |
| 4 workers | 4 | 5 |

Las pruebas utilizaron el mismo escenario de Artillery, con una duración aproximada de seis minutos y un incremento progresivo de la carga, desde 2 hasta 12 usuarios virtuales por segundo.

Cada ejecución se dividió en tres fases: carga baja, media y alta. Esto permitió observar cómo cambiaba el comportamiento de los servidores a medida que aumentaba la cantidad de solicitudes.

#### 5.3.2. Resultados de Artillery

**Resumen general**

| Indicador | 1 worker | 2 workers | 4 workers |
|---|---:|---:|---:|
| Solicitudes HTTP registradas | 9.126 | 8.414 | 7.959 |
| Respuestas HTTP 200 | 4.274 | 2.826 | 2.677 |
| Respuestas HTTP 503 | 3.871 | 4.487 | 4.100 |
| Respuestas HTTP 401 | 0 | 1 | 1 |
| Errores ECONNRESET | 1 | 3 | 0 |
| Errores ERR_SOCKET_TIMEOUT | 980 | 1.097 | 1.181 |
| Usuarios virtuales creados | 2.520 | 2.520 | 2.520 |
| Usuarios virtuales completados | 1.539 | 1.420 | 1.339 |
| Usuarios virtuales fallidos | 981 | 1.100 | 1.181 |

Las tres configuraciones presentaron una cantidad considerable de respuestas HTTP 503 y errores de timeout. Esto indica que una parte importante de las solicitudes no pudo ser atendida correctamente bajo las condiciones de carga aplicadas.

La proporción de respuestas 503 respecto al total de respuestas HTTP registradas fue aproximadamente:

| Configuración | Respuestas 503 | Total de respuestas HTTP | Porcentaje de respuestas 503 |
|---|---:|---:|---:|
| 1 worker | 3.871 | 8.145 | 47,53 % |
| 2 workers | 4.487 | 7.314 | 61,35 % |
| 4 workers | 4.100 | 6.778 | 60,49 % |

En las tres ejecuciones, los errores 503 representaron una parte importante de las respuestas recibidas. Además, aumentó la cantidad de usuarios virtuales fallidos al pasar de uno a cuatro workers.

**Latencia global**

| Indicador (ms) | 1 worker | 2 workers | 4 workers |
|---|---:|---:|---:|
| Tiempo medio | 671,1 | 350,7 | 231 |
| Mediana | 4 | 1 | 1 |
| Percentil 95 (p95) | 4.965,3 | 3.072,4 | 727,9 |
| Percentil 99 (p99) | 7.260,8 | 6.702,6 | 5.944,6 |
| Tiempo máximo | 7.984 | 7.999 | 7.984 |

Aunque las estadísticas globales muestran una reducción del tiempo medio y del p95 al incrementar los workers, estos resultados deben interpretarse junto con la cantidad de respuestas 503 y los errores de timeout.

Las respuestas fallidas pueden recibirse rápidamente y reducir la latencia global calculada por Artillery. Por esta razón, una latencia global menor no significa necesariamente que las solicitudes exitosas hayan mejorado en la misma proporción.

**Latencia de las respuestas exitosas (2xx)**

| Indicador (ms) | 1 worker | 2 workers | 4 workers |
|---|---:|---:|---:|
| Tiempo medio | 1.278,4 | 906,4 | 583,7 |
| Mediana | 50,9 | 21,1 | 10,9 |
| Percentil 95 (p95) | 6.439,7 | 5.487,5 | 4.965,3 |
| Percentil 99 (p99) | 7.557,1 | 7.557,1 | 7.260,8 |

Al considerar únicamente las respuestas exitosas, se observa una reducción progresiva de los tiempos de respuesta al aumentar los workers. Sin embargo, incluso con cuatro workers, el p95 permaneció cercano a los cinco segundos. Esto indica que todavía existían solicitudes exitosas con tiempos de respuesta elevados.

Por tanto, el incremento de workers mejoró algunos indicadores de latencia de las solicitudes exitosas, pero no resolvió los problemas de disponibilidad ni la cantidad de errores registrados.

#### 5.3.3. Uso de CPU y memoria

**Consumo promedio de CPU por fase**

Los valores representan núcleos utilizados por cada backend, teniendo en cuenta que cada contenedor tenía un límite de un núcleo.

| Configuración | Backend | Carga baja | Carga media | Carga alta |
|---|---|---:|---:|---:|
| 1 worker | backend1 | 0,224 | 0,525 | 0,968 |
| | backend2 | 0,241 | 0,534 | 0,965 |
| | backend3 | 0,261 | 0,526 | 0,972 |
| 2 workers | backend1 | 0,243 | 0,487 | 0,996 |
| | backend2 | 0,263 | 0,517 | 0,997 |
| | backend3 | 0,251 | 0,498 | 0,992 |
| 4 workers | backend1 | 0,377 | 0,638 | 1,000 |
| | backend2 | 0,618 | 0,844 | 1,000 |
| | backend3 | 0,747 | 1,000 | 0,997 |

En las tres configuraciones se observó un incremento del consumo de CPU a medida que aumentaba la carga.

Con un worker, los servidores alcanzaron aproximadamente entre el 96 % y el 97 % de utilización promedio durante la fase alta. Con dos workers, el consumo se acercó al 100 %. Con cuatro workers, los tres servidores llegaron prácticamente al límite de un núcleo, e incluso backend2 y backend3 alcanzaron el 100 % en alguna fase.

Estos resultados muestran que el aumento de workers no elimina la limitación de CPU. Por el contrario, una mayor cantidad de procesos puede incrementar la competencia por los recursos disponibles cuando el contenedor tiene asignado un único núcleo.

**Consumo promedio de memoria por fase**

| Configuración | Backend | Carga baja (MB) | Carga media (MB) | Carga alta (MB) |
|---|---|---:|---:|---:|
| 1 worker | backend1 | 71,34 | 72,79 | 67,11 |
| | backend2 | 71,53 | 73,21 | 65,41 |
| | backend3 | 71,41 | 72,06 | 67,61 |
| 2 workers | backend1 | 98,44 | 102,37 | 105,38 |
| | backend2 | 97,45 | 104,55 | 111,66 |
| | backend3 | 93,28 | 98,81 | 110,07 |
| 4 workers | backend1 | 103,96 | 113,86 | 185,21 |
| | backend2 | 103,19 | 107,72 | 186,63 |
| | backend3 | 114,13 | 120,49 | 174,03 |

El consumo de memoria aumentó al incrementar la cantidad de workers. La diferencia fue especialmente visible con cuatro workers durante la fase alta, cuando los servidores alcanzaron promedios aproximados entre 174 y 187 MB.

A pesar de este incremento, los valores permanecieron por debajo del límite de 384 MB asignado a cada contenedor. Por tanto, la CPU representó una limitación más evidente que la memoria durante estas pruebas.

#### 5.3.4. Comportamiento de HAProxy y la base de datos

Las métricas de HAProxy mostraron un aumento considerable en los tiempos de respuesta de los backends durante las fases de mayor carga.

En la configuración de un worker, los promedios de respuesta durante la fase alta estuvieron aproximadamente entre 4.960 y 5.258 ms. Con dos workers, se encontraron valores entre 5.902 y 7.252 ms. Con cuatro workers, los valores estuvieron entre 5.091 y 6.001 ms.

Estos resultados reflejan que los tiempos de atención aumentaron considerablemente bajo carga elevada, aunque las diferencias entre configuraciones no fueron suficientes para establecer que una cantidad de workers solucionara el problema.

En cuanto a la base de datos, el uso de conexiones aumentó con la cantidad de workers:

- Con un worker, se utilizaron aproximadamente el 13 % de las conexiones disponibles.
- Con dos workers, el uso se mantuvo alrededor del 25 %.
- Con cuatro workers, alcanzó aproximadamente el 49 %.

Aunque el consumo de conexiones aumentó, no se llegó al límite configurado de 100 conexiones. Esto indica que, en estas ejecuciones, la saturación de conexiones de PostgreSQL no fue el principal indicador de limitación.

Las métricas de colas de HAProxy permanecieron en cero. Sin embargo, esto no significa que el sistema estuviera libre de problemas: cuando un servidor deja de estar disponible, HAProxy puede retirarlo temporalmente del grupo de servidores disponibles, y las solicitudes también pueden terminar en errores o tiempos de espera.

#### 5.3.5. Eventos y alertas de disponibilidad

Durante las pruebas de workers se presentaron episodios de indisponibilidad en los servidores backend. Datadog detectó individualmente los eventos de caída y recuperación, y envió las notificaciones correspondientes al correo electrónico.

En la primera ejecución con un worker, los registros muestran el siguiente comportamiento:

| Hora (UTC) | Evento | Interpretación |
|---|---|---|
| 15:11:21 | Alerta de tasa elevada de errores HTTP 5xx | Se superó el umbral configurado para los errores del clúster. |
| 15:12:07 | Caída de backend2 y backend3 | Datadog detectó ambos servidores como no disponibles. |
| 15:12:09 | Alerta de problemas en las reservas | Se detectaron dificultades en las solicitudes de reserva. |
| 15:13:09 | Recuperación de la alerta de reservas | La condición que activaba la alerta dejó de presentarse. |
| 15:13:21 | Nueva alerta de errores HTTP 5xx | La tasa de errores volvió a superar el umbral. |
| 15:14:07 | Caída de backend1 | Datadog detectó la indisponibilidad del tercer servidor. |
| 15:15:07 | Recuperación de backend1, backend2 y backend3 | Los monitores notificaron la recuperación de los tres servidores. |

Los registros permiten observar que los tres backends presentaron eventos de caída durante esta ejecución, aunque no se puede afirmar que los tres estuvieran indisponibles simultáneamente. Backend2 y backend3 fueron detectados como caídos a las 15:12:07, mientras que backend1 fue reportado posteriormente, a las 15:14:07.

En las ejecuciones posteriores también se registraron interrupciones. En la segunda ejecución se detectaron caídas de backend1 y backend3 en diferentes momentos. En la tercera ejecución se notificó la caída de backend1 y backend3.

Estos eventos estuvieron acompañados de respuestas HTTP 503 y errores de timeout registrados por Artillery. Las alertas permitieron identificar los servidores afectados y comprobar que Datadog notificaba los cambios de disponibilidad.

Es importante distinguir entre la hora en que se genera una alerta y el instante exacto en que comienza una interrupción. El monitor necesita cumplir sus condiciones de evaluación antes de generar una notificación.

#### 5.3.6. Análisis comparativo

Al comparar las tres configuraciones se identifican los siguientes comportamientos:

- **Latencia:** al aumentar los workers, disminuyeron los tiempos medios y los percentiles de las respuestas exitosas. Sin embargo, los tiempos p95 continuaron siendo elevados.
- **Errores:** las tres configuraciones presentaron una proporción considerable de respuestas HTTP 503 y errores de timeout. La configuración de dos workers registró el mayor porcentaje de respuestas 503.
- **CPU:** los tres backends alcanzaron valores cercanos al 100 % durante las fases de mayor carga, independientemente de la cantidad de workers.
- **Memoria:** el consumo aumentó con la cantidad de workers, especialmente con cuatro, aunque permaneció por debajo del límite asignado.
- **Disponibilidad:** se presentaron caídas de los servidores backend en las diferentes ejecuciones, detectadas por los monitores de Datadog.
- **Base de datos:** el uso de conexiones aumentó al incrementar los workers, pero no alcanzó el máximo configurado.

En consecuencia, aunque aumentar los workers permitió reducir algunos tiempos de respuesta de las solicitudes exitosas, no fue suficiente para garantizar la estabilidad del clúster. El límite de CPU y los episodios de indisponibilidad continuaron afectando el procesamiento de las solicitudes.

---

### 5.4. Experimentos con diferentes tiempos de espera entre solicitudes

#### 5.4.1. Objetivo y configuración

Este grupo de experimentos buscó evaluar cómo influye el tiempo de espera entre las solicitudes de un mismo usuario virtual en el ritmo de generación de tráfico, la duración de las sesiones y los tiempos de respuesta del sistema.

Se compararon tres escenarios:

| Prueba | Configuración de las pausas | Etiqueta de Artillery |
|---|---|---|
| Sin pausas | Las solicitudes se ejecutan sin esperas adicionales | `pausas-sin` |
| Pausas de 1 a 3 segundos | Se agrega una espera aleatoria entre 1.000 y 2.999 ms | `pausas-1a3` |
| Pausas de 5 segundos | Se agrega una espera de cinco segundos entre solicitudes | `pausas-5s` |

Las tres ejecuciones utilizaron el mismo flujo de operaciones y generaron la misma cantidad de usuarios virtuales y solicitudes. Cada prueba registró:

- 780 usuarios virtuales creados.
- 780 usuarios virtuales completados.
- 0 usuarios virtuales fallidos.
- 10.140 solicitudes HTTP.
- 10.140 respuestas HTTP 200.

Cada usuario virtual realizó operaciones de inicio de sesión, consulta de cartelera, consulta de evento y consulta de sillas. Las métricas por endpoint permiten comparar el comportamiento de estas operaciones entre los tres escenarios.

#### 5.4.2. Resultados generales de Artillery

| Indicador | Sin pausas | Pausas de 1 a 3 s | Pausas de 5 s |
|---|---:|---:|---:|
| Solicitudes HTTP | 10.140 | 10.140 | 10.140 |
| Respuestas HTTP 200 | 10.140 | 10.140 | 10.140 |
| Usuarios creados | 780 | 780 | 780 |
| Usuarios completados | 780 | 780 | 780 |
| Usuarios fallidos | 0 | 0 | 0 |
| Solicitudes por segundo | 21 | 18 | 16 |
| Tiempo medio de respuesta (ms) | 59,1 | 76,2 | 81,4 |
| Mediana (ms) | 6 | 7 | 7 |
| Percentil 95 (p95) (ms) | 383,8 | 539,2 | 539,2 |
| Percentil 99 (p99) (ms) | 854,2 | 1.274,3 | 1.274,3 |
| Tiempo máximo (ms) | 7.210 | 4.329 | 5.795 |

Las tres ejecuciones completaron todas las solicitudes con respuestas HTTP 200 y sin usuarios virtuales fallidos. Por tanto, no se observaron errores de ejecución en los escenarios evaluados.

La cantidad total de solicitudes se mantuvo constante, pero el ritmo de generación disminuyó al incorporar pausas: pasó de 21 solicitudes por segundo sin pausas a 18 con pausas de uno a tres segundos y a 16 con pausas de cinco segundos.

El tiempo medio de respuesta aumentó de 59,1 ms a 76,2 ms y 81,4 ms, respectivamente. Sin embargo, esta diferencia debe interpretarse junto con las métricas por endpoint, porque el tiempo global incluye el inicio de sesión, que tiene un costo considerablemente mayor que las consultas.

#### 5.4.3. Duración de las sesiones y comportamiento de las pausas

La duración de las sesiones permite observar directamente el efecto de los tiempos de espera configurados:

| Indicador (ms) | Sin pausas | Pausas de 1 a 3 s | Pausas de 5 s |
|---|---:|---:|---:|
| Duración mínima | 374,7 | 18.655,6 | 60.381,6 |
| Duración media | 804,5 | 25.120,6 | 61.121,9 |
| Mediana | 550,1 | 25.091,6 | 60.495,1 |
| p95 | 2.101,1 | 28.290,8 | 62.964 |
| p99 | 4.867 | 30.040,3 | 65.533,7 |
| Duración máxima | 8.272,6 | 32.231,4 | 66.302,4 |

Los resultados muestran una diferencia clara entre las tres configuraciones:

- **Sin pausas:** las sesiones tuvieron una duración media aproximada de 0,8 segundos. Los usuarios virtuales ejecutaron las operaciones de manera consecutiva, sin esperas adicionales.
- **Pausas de 1 a 3 segundos:** la duración media aumentó a aproximadamente 25,1 segundos, debido a las esperas aleatorias entre solicitudes.
- **Pausas de 5 segundos:** las sesiones alcanzaron una duración media aproximada de 61,1 segundos, como consecuencia de los tiempos de espera más prolongados.

En la prueba de pausas de uno a tres segundos también se registró la métrica personalizada `pausa.ms`, que permitió comprobar los tiempos de espera aplicados:

| Indicador | Resultado |
|---|---:|
| Pausa mínima | 1.000 ms |
| Pausa máxima | 2.999 ms |
| Pausa media | 2.006,5 ms |
| Mediana | 2.018,7 ms |
| p95 | 2.893,5 ms |
| p99 | 2.951,9 ms |

Estos valores coinciden con el intervalo de pausas configurado. En los otros escenarios, la duración de las sesiones también refleja el comportamiento esperado de sus respectivos tiempos de espera.

#### 5.4.4. Latencia por tipo de petición

La comparación por endpoint permite identificar qué operaciones tuvieron mayor influencia en los tiempos globales.

**Tiempo medio de respuesta (ms)**

| Endpoint | Sin pausas | Pausas de 1 a 3 s | Pausas de 5 s |
|---|---:|---:|---:|
| Cartelera | 11,8 | 13,1 | 18,4 |
| Evento | 9,6 | 13,2 | 20,8 |
| Inicio de sesión | 611,7 | 816,1 | 777,7 |
| Sillas por zona | 17,7 | 17,3 | 31 |

**Percentil 95 (p95) (ms)**

| Endpoint | Sin pausas | Pausas de 1 a 3 s | Pausas de 5 s |
|---|---:|---:|---:|
| Cartelera | 22 | 49,9 | 55,2 |
| Evento | 30,3 | 51,9 | 49,9 |
| Inicio de sesión | 1.556,5 | 1.939,5 | 2.186,8 |
| Sillas por zona | 51,9 | 62,2 | 63,4 |

**Percentil 99 (p99) (ms)**

| Endpoint | Sin pausas | Pausas de 1 a 3 s | Pausas de 5 s |
|---|---:|---:|---:|
| Cartelera | 82,3 | 92,8 | 247,2 |
| Evento | 76 | 85,6 | 262,5 |
| Inicio de sesión | 3.678,4 | 2.893,5 | 4.065,2 |
| Sillas por zona | 94,6 | 94,6 | 507,8 |

El inicio de sesión fue la operación con mayor tiempo de respuesta en los tres escenarios. Su tiempo medio estuvo entre 611,7 y 816,1 ms, mientras que las consultas de cartelera, evento y sillas presentaron medias considerablemente menores.

Esto se relaciona con el procesamiento de las credenciales y el cálculo del hash de contraseña. Por esa razón, el tiempo global de respuesta está influido considerablemente por las operaciones de autenticación.

En las pruebas con pausas se observa un aumento de algunos tiempos de respuesta de las consultas. Por ejemplo, el tiempo medio de consulta de evento pasó de 9,6 ms sin pausas a 20,8 ms con pausas de cinco segundos. Asimismo, el p99 de la consulta de sillas pasó de 94,6 ms a 507,8 ms.

Sin embargo, estos resultados no permiten concluir que las pausas por sí solas causaron el aumento de latencia. Las ejecuciones se realizaron en momentos diferentes y pueden existir variaciones en el estado de los contenedores, la base de datos y la infraestructura durante cada corrida.

#### 5.4.5. Análisis comparativo

Los resultados permiten identificar tres comportamientos principales:

- **Ritmo de solicitudes:** al aumentar el tiempo de espera entre operaciones, disminuyó la cantidad de solicitudes generadas por segundo. Esto es coherente con la configuración de los escenarios.
- **Duración de las sesiones:** las pausas incrementaron considerablemente el tiempo que cada usuario virtual permaneció ejecutando su flujo. La duración media pasó de 0,8 segundos sin pausas a 25,1 segundos con pausas de uno a tres segundos y 61,1 segundos con pausas de cinco segundos.
- **Tiempos de respuesta:** las medianas globales permanecieron bajas, entre 6 y 7 ms, pero las medias y los percentiles altos aumentaron en los escenarios con pausas. El inicio de sesión continuó siendo la operación más costosa.

Es importante tener en cuenta que una pausa entre solicitudes no representa tiempo de procesamiento del servidor. Es un tiempo de espera introducido por el propio escenario de Artillery. Por tanto, la duración de las sesiones aumenta aunque el servidor no esté trabajando durante esos intervalos.

En general, las tres configuraciones completaron satisfactoriamente los flujos. La prueba sin pausas generó el mayor ritmo de solicitudes, mientras que las pruebas con pausas representaron un comportamiento en el que los usuarios esperan antes de continuar con sus operaciones.

---

### 5.5. Experimentos de concurrencia en las reservas

#### 5.5.1. Objetivo y configuración

El objetivo de este grupo de pruebas fue comprobar cómo responde el sistema cuando varios usuarios intentan reservar sillas simultáneamente, tanto cuando compiten por el mismo recurso como cuando solicitan recursos diferentes.

Se realizaron dos escenarios:

| Prueba | Configuración | Etiqueta en Datadog |
|---|---|---|
| Concurrencia sobre una misma silla | 50 solicitudes intentan reservar la silla 2051 | `concurrencia_misma_silla` |
| Concurrencia sobre sillas diferentes | 50 solicitudes intentan reservar 50 sillas distintas | `concurrencia_distribuida` |

En ambas pruebas se generaron 50 usuarios virtuales en aproximadamente un segundo, utilizando una sesión autenticada compartida para las solicitudes. Por tanto, se evaluaron 50 intentos concurrentes de reserva, pero no 50 cuentas de usuario diferentes.

El flujo de reserva utiliza una actualización condicional en PostgreSQL, que modifica el estado de una silla únicamente cuando todavía se encuentra disponible. La operación de actualización y la creación de la reserva se realizan dentro de una transacción.

Esta condición permite que, cuando varias solicitudes intentan reservar la misma silla, solamente una pueda confirmar la operación. Las demás reciben una respuesta de conflicto si la silla ya no está disponible.

#### 5.5.2. Resultados de Artillery

| Indicador | Misma silla | Sillas diferentes |
|---|---:|---:|
| Usuarios virtuales creados | 50 | 50 |
| Usuarios virtuales completados | 50 | 50 |
| Usuarios virtuales fallidos | 0 | 0 |
| Solicitudes | 50 | 50 |
| Respuestas HTTP 201 | 1 | 50 |
| Respuestas HTTP 409 | 49 | 0 |
| Tasa de solicitudes | 50 req/s | 50 req/s |
| Tiempo medio (ms) | 15,3 | 14,8 |
| Mediana (ms) | 7,9 | 7,9 |
| p95 (ms) | 44,3 | 61 |
| p99 (ms) | 56,3 | 74,4 |
| Tiempo máximo (ms) | 76 | 77 |

**Concurrencia sobre una misma silla**

De los 50 intentos realizados sobre la silla 2051, uno recibió HTTP 201 y los otros 49 recibieron HTTP 409.

Esto representa el comportamiento esperado: la primera solicitud que consiguió confirmar la reserva modificó el estado de la silla y las demás solicitudes fueron rechazadas al encontrar que el recurso ya no estaba disponible.

No se registraron usuarios virtuales fallidos, ya que las respuestas HTTP 409 corresponden a un resultado controlado por la aplicación y no a un fallo de ejecución de Artillery.

**Concurrencia sobre sillas diferentes**

En el escenario distribuido, las 50 solicitudes utilizaron identificadores de sillas diferentes. Todas recibieron HTTP 201 y no se presentaron conflictos HTTP 409.

Esto demuestra que el sistema pudo procesar las reservas independientes de manera simultánea, sin impedir que las demás operaciones se completaran.

#### 5.5.3. Resultados del monitoreo con Datadog

El análisis de Datadog permitió complementar los resultados de Artillery y observar el comportamiento de los componentes durante las dos ejecuciones.

**Distribución de solicitudes entre los backends**

| Escenario | backend1 | backend2 | backend3 |
|---|---:|---:|---:|
| Misma silla | 34,2 % | 32,9 % | 32,9 % |
| Sillas diferentes | 33,8 % | 32,5 % | 33,8 % |

HAProxy mantuvo una distribución equilibrada del tráfico en ambos escenarios. Ninguno de los backends concentró una proporción significativamente mayor de solicitudes.

**Consumo de recursos durante las pruebas**

| Escenario | Backend | CPU promedio (núcleos) | Memoria promedio (MB) |
|---|---|---:|---:|
| Misma silla | backend1 | 0,031 | 93,5 |
| | backend2 | 0,032 | 95,7 |
| | backend3 | 0,032 | 93,8 |
| Sillas diferentes | backend1 | 0,034 | 93,8 |
| | backend2 | 0,032 | 96,1 |
| | backend3 | 0,032 | 94,3 |

Los tres backends mantuvieron un consumo bajo frente a los límites asignados de un núcleo de CPU y 384 MB de memoria por contenedor.

**Comportamiento de HAProxy y PostgreSQL**

En las dos ejecuciones:

- No se registraron respuestas HTTP 5xx en las métricas de HAProxy.
- Las colas de los tres backends permanecieron en cero.
- El uso de conexiones de PostgreSQL se mantuvo en el 25 % del máximo configurado de 100 conexiones.
- El tráfico continuó distribuyéndose entre los tres servidores backend.

En el escenario distribuido, la métrica de sillas actualizadas llegó a un máximo de 3,34 filas por segundo. Esto es coherente con la actividad de actualización de las reservas durante la ventana de medición.

No se obtuvieron datos para la métrica agregada de bloqueos por tabla. Esto no permite afirmar que PostgreSQL no utilizó bloqueos durante las transacciones, ya que las actualizaciones concurrentes pueden involucrar bloqueos de fila que no necesariamente quedan representados en esa métrica.

#### 5.5.4. Análisis comparativo

Los dos escenarios comprobaron comportamientos diferentes y complementarios:

- **Integridad de las reservas:** cuando 50 solicitudes compitieron por una misma silla, solamente una consiguió confirmarla. Las otras 49 recibieron un conflicto controlado.
- **Procesamiento de operaciones independientes:** cuando las solicitudes se distribuyeron entre 50 sillas diferentes, todas las reservas se completaron correctamente.
- **Distribución del tráfico:** HAProxy mantuvo un reparto cercano a un tercio del tráfico para cada backend.
- **Recursos:** el consumo de CPU y memoria permaneció bajo y no se observaron señales de saturación en los contenedores.
- **Disponibilidad:** no se registraron respuestas HTTP 5xx ni acumulación de solicitudes en las colas de HAProxy.

Las latencias fueron similares en ambos escenarios. Aunque el p95 y el p99 fueron algo mayores en la prueba distribuida, la diferencia en el tiempo máximo fue de apenas un milisegundo.

En conjunto, estos resultados muestran que el sistema pudo controlar la competencia por un mismo recurso y procesar reservas independientes sin errores de ejecución.

---

### 5.6. Conclusiones de los experimentos

Los experimentos permitieron observar el comportamiento del clúster bajo diferentes distribuciones de operaciones, configuraciones de Gunicorn, tiempos de espera y condiciones de concurrencia.

- En las pruebas de proporciones, el aumento de la cantidad de reservas estuvo acompañado de un incremento en los tiempos medios y en los percentiles de respuesta, principalmente por el costo de las operaciones de autenticación.
- La distribución de HAProxy se mantuvo equilibrada entre los tres backends durante las pruebas de proporciones, sin presentar errores 5xx ni acumulación de solicitudes en las colas.
- En las pruebas de workers, aumentar la cantidad de procesos permitió reducir algunos tiempos de respuesta de las solicitudes exitosas, pero no eliminó los errores HTTP 503 ni los problemas de disponibilidad.
- La CPU fue uno de los principales recursos limitantes durante las pruebas de workers, ya que los tres backends alcanzaron valores cercanos al 100 % de utilización durante las fases de mayor carga.
- El consumo de memoria aumentó con la cantidad de workers, especialmente en la configuración de cuatro, aunque permaneció dentro del límite asignado a los contenedores.
- En las pruebas con pausas, el aumento de los tiempos de espera redujo el ritmo de generación de solicitudes y prolongó la duración de las sesiones. Las tres ejecuciones completaron todos los usuarios virtuales y obtuvieron respuestas HTTP 200.
- En las pruebas de concurrencia, el sistema permitió una sola reserva cuando 50 solicitudes compitieron por la misma silla y confirmó las 50 reservas cuando se utilizaron sillas diferentes.
- Datadog permitió observar la distribución del tráfico, el consumo de recursos y los indicadores de disponibilidad durante las pruebas de concurrencia.
- Los resultados muestran que la cantidad de workers, los tiempos de espera y la distribución de las operaciones deben analizarse teniendo en cuenta tanto el comportamiento de la aplicación como los recursos asignados a cada contenedor.

En general, los experimentos permitieron identificar las condiciones en las que el clúster mantiene un comportamiento estable y aquellas en las que aparecen limitaciones de procesamiento o disponibilidad. También permitieron comprobar que el mecanismo de reservas controla los intentos concurrentes sobre un mismo recurso sin impedir las reservas independientes.

### 5.7. Evidencias

Las evidencias de los experimentos se encuentran en las siguientes carpetas:

- `evidencias/pruebas/04-experimentos/`: resultados y capturas de Artillery y Datadog correspondientes a las pruebas.
- `reportes_datadog/`: reportes HTML y resultados generados por el análisis de Datadog.
- `artillery/`: archivos de configuración y scripts utilizados para ejecutar los escenarios de rendimiento, pausas y concurrencia.

---

## 6. Conclusiones generales

Las pruebas permitieron verificar la integración de Artillery con Datadog mediante DogStatsD, comprobando la recepción de métricas y eventos generados durante las ejecuciones.

Los escenarios de errores controlados demostraron que la aplicación responde con los códigos HTTP esperados ante solicitudes inválidas y errores internos. Además, se verificó que el monitor de errores 5xx detecta el incremento de fallos, genera las notificaciones correspondientes y se recupera cuando la condición deja de presentarse.

Las pruebas de caída y recuperación comprobaron que HAProxy detecta la indisponibilidad de un backend y redistribuye el tráfico entre los servidores disponibles. Datadog permitió identificar y notificar tanto las caídas como las recuperaciones.

Los experimentos de rendimiento mostraron que la distribución de consultas y reservas influye en los tiempos de respuesta, principalmente por el costo del proceso de autenticación. También se identificó que aumentar la cantidad de workers puede reducir algunos tiempos de respuesta, pero no garantiza una mayor estabilidad cuando los recursos de CPU son limitados.

Las pruebas con pausas permitieron observar cómo los tiempos de espera entre operaciones modifican el ritmo de generación de solicitudes y la duración de las sesiones. Las tres configuraciones completaron satisfactoriamente sus solicitudes, sin usuarios virtuales fallidos.

Finalmente, las pruebas de concurrencia comprobaron que el sistema controla correctamente los intentos simultáneos de reserva: evita que varias solicitudes confirmen la misma silla y permite que se completen reservas sobre sillas diferentes.

En conjunto, los resultados muestran que la infraestructura monitoreada puede responder ante diferentes condiciones de carga y disponibilidad. Artillery permitió generar escenarios controlados y medir el comportamiento de las solicitudes, mientras que Datadog proporcionó información útil para observar los componentes del clúster, detectar problemas y analizar su comportamiento.
