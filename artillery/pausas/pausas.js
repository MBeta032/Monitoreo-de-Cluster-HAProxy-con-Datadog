'use strict';
// pausa aleatoria entre acciones de un mismo usuario virtual.
// Uso en el flujo: - function: "pausaAleatoria"
// Rango por defecto 1 a 3 s; se puede cambiar con PAUSA_MIN_S y PAUSA_MAX_S.
const MIN_S = Number(process.env.PAUSA_MIN_S || 1);
const MAX_S = Number(process.env.PAUSA_MAX_S || 3);

function pausaAleatoria(context, events, done) {
  const ms = Math.round((MIN_S + Math.random() * (MAX_S - MIN_S)) * 1000);
  // Registra la pausa real para comprobar en el reporte que se aplicó.
  events.emit('histogram', 'pausa.ms', ms);
  setTimeout(done, ms);
}

module.exports = { pausaAleatoria };