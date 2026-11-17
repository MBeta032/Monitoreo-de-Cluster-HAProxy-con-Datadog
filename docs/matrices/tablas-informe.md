# Tablas compactas para el informe IEEE (sección III, Alternativas de solución)

Copiar tal cual. Los números salen de [`matriz-decision.xlsx`](matriz-decision.xlsx) y de `ENTREGA\datos-medidos.md`. Puntajes de 1 a 5 (5 = mejor). "Est." = estimado, no medido. Las referencias [n] siguen la lista de [`matrices.md`](matrices.md) §7; el Redactor las renumera por orden de aparición.

## TABLA I · Restricciones del cliente

| Componente | Requisito del PDF | Evidencia de ajuste |
|---|---|---|
| HAProxy 2.6 | ≥ 3 backends, estadísticas, socket Unix, logs estructurados | DOWN a 5-6 s con `inter 1s fall 3`; socket `level user` |
| Datadog Agent 7.85.1 | `haproxy.d`, logs, dashboard, ≥ 2 monitores | 3 monitores; `[Triggered]` a 60 s de la caída |
| Docker Compose | Nada en el host; configs montadas | 7 servicios; volumen de socket compartido |

## TABLA II · Matriz 1: algoritmo de balanceo (3 × 300 s a 2 VU/s)

| Criterio (cómo se mide) | Peso | RR | LC |
|---|---:|---:|---:|
| Latencia p95, mediana de 3 corridas (ms) | 25 % | 5 (106,7) | 5 (108,9) |
| Flujos completos (%) | 20 % | 5 (99,94) | 5 (100) |
| Throughput (req/s) | 10 % | 5 (8,021) | 5 (8,022) |
| Adecuación a HTTP corto [1] | 15 % | 5 | 3 |
| Saturación (RR medido; LC est.) | 15 % | 3 | 4 |
| Reparto verificable (RR 31/34/34 %; LC est.) | 5 % | 5 | 4 |
| Riesgo de cambio antes de la demo (est.) | 10 % | 5 | 3 |
| **Puntaje ponderado** | | **4,70** | **4,30** |

## TABLA III · Matriz 2: workers de Gunicorn (rampa 2-12 VU/s, 1 CPU y 384 MB)

| Criterio (cómo se mide) | Peso | 1 | 2 | 4 |
|---|---:|---:|---:|---:|
| Respuestas 200 / respuestas (%) | 25 % | 5 (52,5) | 2 (38,6) | 3 (39,5) |
| VU completados (%) | 10 % | 5 (61,1) | 4 (56,3) | 4 (53,1) |
| p95 de respuestas 2xx (s) | 20 % | 2 (6,44) | 4 (5,49) | 5 (4,97) |
| Memoria máxima / 384 MB (%) | 15 % | 5 (19,1) | 4 (29,1) | 3 (48,6) |
| Conexiones PostgreSQL (%) | 10 % | 5 (13) | 4 (25) | 3 (49) |
| CPU con carga baja / 1 núcleo (%) | 10 % | 4 (24,2) | 4 (25,2) | 3 (58,1) |
| Distancia a 2 × núcleos + 1 [6] | 10 % | 3 (2) | 4 (1) | 4 (1) |
| **Puntaje ponderado** | | **4,10** | **3,50** | **3,60** |

## TABLA IV · Matriz 3: formato de logs

| Criterio (cómo se mide) | Peso | JSON | syslog |
|---|---:|---:|---:|
| Parseo sin pipeline [5] (syslog est.) | 30 % | 5 | 4 |
| Campos con nombre (JSON 15; syslog est.) | 20 % | 5 | 4 |
| Bytes por línea, mediana (JSON medido; syslog est.) | 15 % | 1 (273) | 5 (165) |
| Coherencia con logs de backends | 10 % | 5 | 3 |
| Robustez ante entradas del cliente (syslog est.) | 10 % | 5 | 4 |
| Directivas en `haproxy.cfg` | 10 % | 3 (3) | 5 (1) |
| Legibilidad en consola (est.) | 5 % | 3 | 4 |
| **Puntaje ponderado** | | **4,10** | **4,15** |

## TABLA V · Matriz 4: lectura del Agent

| Criterio (cómo se mide) | Peso | Socket | Stats HTTP | Prometheus |
|---|---:|---:|---:|---:|
| Requisito literal del PDF | 30 % | 5 | 1 | 1 |
| Service check `backend_up` [4] | 20 % | 5 | 5 | 3 |
| Puertos TCP abiertos (0 / 1 / 1) | 15 % | 5 | 3 | 3 |
| Recomendación de Datadog [4] | 15 % | 2 | 2 | 5 |
| Costo de generación [3] | 10 % | 5 | 5 | 2 |
| Riesgo de cambio (est.) | 10 % | 5 | 4 | 2 |
| **Puntaje ponderado** | | **4,55** | **2,95** | **2,50** |

## TABLA VI · Resultado y sensibilidad

| Decisión | Gana la matriz | Implementado | ¿Coincide? | Qué voltea la decisión |
|---|---|---|---|---|
| Balanceo | RR (4,70 / 4,30) | RR | Sí | Saturación de 15 % a 39,3 % |
| Workers | 1 (4,10 / 3,60 / 3,50) | 2 | No | p95 2xx de 20 % a 31,4 % (gana 4); éxito de 25 % a 6,3 % (gana 2) |
| Logs | syslog (4,15 / 4,10) | JSON | No (empate técnico) | Tamaño de 15 % a 13,9 %, o syslog con 3 en parseo |
| Lectura del Agent | Socket (4,55 / 2,95 / 2,50) | Socket | Sí | Recomendación de Datadog de 15 % a 49,5 % |

## Pies de figura

- **Fig. n.** Latencia p95 por repetición con Round Robin y LeastConn. (a) Taquilla con PostgreSQL, 2 VU/s durante 300 s; (b) backend simple histórico, 20 VU/s durante 300 s. Archivo `docs/matrices/fig-rr-vs-leastconn.png`, 8,9 × 5,2 cm.
- **Fig. n+1.** Efecto de 1, 2 y 4 workers de Gunicorn por backend bajo una rampa de 2 a 12 VU/s: (a) respuestas 200, (b) p95 de respuestas 2xx, (c) memoria máxima por backend. El círculo es la repetición de 2 workers. Archivo `docs/matrices/fig-workers.png`, 8,9 × 5,0 cm.

## Texto corto de reflexión (para pegar, 1 párrafo por matriz)

- **Balanceo.** RR y LeastConn rinden igual con carga normal (2 % de diferencia en p95, menos que la variación entre repeticiones de RR). Se elige RR por la recomendación de HAProxy para HTTP corto y porque P3 ya se midió con él; LeastConn queda por probar en saturación.
- **Workers.** La matriz favorece 1 worker porque, con 1 CPU por contenedor y la CPU saturada, más procesos compiten por el núcleo. Se mantienen 2 workers porque toda la evidencia de P1 a P5 se midió así, con carga normal tuvieron 0 errores 5xx y Gunicorn recomienda varios workers para aislar fallos. Mejora futura: 3 repeticiones por debajo de la saturación.
- **Logs.** Empate técnico: syslog solo gana por tamaño (unos 108 B menos por línea), y sus ventajas en parseo son estimadas. JSON se mantiene porque su parseo y sus 15 campos están verificados en el dashboard.
- **Lectura del Agent.** El socket gana incluso sin el requisito del PDF, por el service check de caída, cero puertos y menor costo. Datadog recomienda Prometheus: es la migración natural si el requisito cambia.
