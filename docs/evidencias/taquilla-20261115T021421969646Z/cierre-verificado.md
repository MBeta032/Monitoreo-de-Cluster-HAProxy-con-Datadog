# Cierre verificado de la campaña de JJ

Campaña: `taquilla-20261115T021421969646Z`.

Se revisaron el manifiesto y los contadores originales de las 14 corridas. El estado es `completada` y la restauración de HAProxy está registrada como `aplicada`. El intervalo total fue el 14 de noviembre de 2026, de 21:14:27 a 22:42:57, hora de Colombia (UTC−5).

El [informe de métricas](20261115T041213186994Z/informe.md) conserva los resultados y las ventanas UTC. Esta nota añade comprobaciones de los JSON y observaciones sobre las capturas aportadas; no sustituye los archivos originales.

## Intensidad y degradación

| Tasa de llegada | Flujos completos / VU creados | VU fallidos | p95 HTTP | HTTP 5xx |
|---|---|---|---|---|
| 10 VU/s | 3000 / 3000 (100 %) | 0 | 228,2 ms | 0 |
| 20 VU/s | 2350 / 6000 (39,17 %) | 3650 | 14621,8 ms | 3634 |
| 40 VU/s | 375 / 12000 (3,125 %) | 11625 | 24107,7 ms | 10603 |
| 60 VU/s | 25 / 18000 (0,139 %) | 17975 | 22703,7 ms | 15132 |

La primera intensidad ensayada con degradación fuerte fue 20 VU/s. El cambio entre el resultado satisfactorio y el degradado quedó acotado entre 10 y 20 VU/s para este perfil y entorno; no se midió el umbral exacto ni se demuestra una capacidad universal.

Los JSON identifican:

- 20 VU/s: 3634 respuestas 503 y 16 ECONNRESET.
- 40 VU/s: 10568 respuestas 503, 35 respuestas 504, 1019 ERR_SOCKET_TIMEOUT y 3 ECONNRESET.
- 60 VU/s: 14964 respuestas 503, 168 respuestas 504, 2841 ERR_SOCKET_TIMEOUT y 2 ECONNRESET.

Las capturas muestran CPU cerca del límite de un núcleo por backend durante el tramo de carga alta, compatible con presión de CPU. No permiten atribuir todos los errores a una causa única. La memoria permanece por debajo del límite dibujado. Una cola de HAProxy en cero no invalida los fallos observados por el cliente.

La caída de la mediana o el aumento de solicitudes/s bajo alta carga no prueban mejor rendimiento: el conjunto incluye respuestas de error y numerosos flujos incompletos. El caudal de solicitudes no equivale al caudal de operaciones de negocio exitosas.

## Patrones, duración y algoritmos

Los patrones escalonado y pico completaron sus flujos sin usuarios fallidos ni 4xx/5xx. Sus volúmenes son menores que el constante a 10 VU/s; sus latencias no deben interpretarse como una comparación a igual volumen.

La corrida de 10 minutos tuvo un ECONNRESET: 1199 de 1200 flujos completos. La de 15 minutos completó 1800 de 1800. Se conserva el fallo aislado; no se conoce su causa raíz con estos contadores.

Round Robin tuvo p95 de 106,7 / 111,1 / 106,7 ms; LeastConn, 108,9 / 108,9 / 111,1 ms. En Round Robin hubo un ECONNRESET en la tercera repetición (599 de 600 flujos completos); las tres de LeastConn completaron 600 de 600. Las latencias son próximas bajo esta carga baja y no justifican un ganador general. No se promedian percentiles para presentar un p95 global.

## Discrepancias de monitoreo pendientes

Las capturas de Datadog mostraron 5xx en cero, mientras los JSON registran numerosos 503/504 en ese intervalo. Debe conservarse esta discrepancia y revisarla con el responsable del dashboard antes de afirmar que el indicador de errores está validado.

En el JSON versionado del dashboard, los widgets de 5xx consultan `haproxy.backend.response.5xx` con el filtro `!backend:backend`. Es un punto concreto para revisar: hay que comprobar el alcance de las series y los errores generados por HAProxy, además de filtros, unidades y denominador. Esto es una hipótesis de revisión, no una causa confirmada ni una comprobación de la consulta actualmente desplegada.

También queda por reconciliar el panel de tráfico de aplicación cercano a 989/s en una ventana anterior con el de HAProxy. No se usan esas cifras como mediciones equivalentes. El panel de consultas lentas sin coincidencias solo indica ausencia de registros para esa consulta y filtro.

Para revisar el tramo de errores, seleccionar el 14 de noviembre de 2026 de 21:19:35 a 21:36:03, hora de Colombia. Vincular las capturas guardadas al informe; las imágenes vistas en la conversación no se han copiado automáticamente a esta carpeta.

## Alcance de la entrega

Los cuatro criterios de la campaña de consultas autenticadas están ejecutados. El informe debe conservar los fallos y limitaciones. La reserva y el CSRF se validan funcionalmente por separado; esta campaña no representa una mezcla de compras ni un ensayo de contención de reservas.

Pendiente para publicar el cierre: adjuntar las capturas, dejar registrada o resolver con el responsable la discrepancia de monitoreo, revisar los archivos preparados para Git y publicar el PR. No es necesario repetir la campaña para documentar estos resultados.
