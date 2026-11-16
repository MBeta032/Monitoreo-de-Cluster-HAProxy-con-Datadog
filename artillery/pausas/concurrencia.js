'use strict';
// Todos los usuarios inician sesión y luego esperan a la siguiente "salva" (un instante común cada
// SALVA_MS) para reservar a la vez. Así los intentos coinciden en el tiempo aunque el login (unos
// 300 ms de CPU cada uno) los escalone al llegar.
//
// Variables de entorno opcionales (se pasan con docker run -e):
//   SALVA_MS=10000         periodo entre salvas
//   SILLA_BASE=1           primera silla usada (el concierto de venta flash va del id 1 al 2000)
//   SILLAS_TOTAL=2000      sillas disponibles desde SILLA_BASE
//   SILLAS_POR_SALVA=2     en "mismas": cuántas sillas se disputan en cada salva
const PERIODO_MS = Number(process.env.SALVA_MS || 10000);
const SILLA_BASE = Number(process.env.SILLA_BASE || 1);
const SILLAS_TOTAL = Number(process.env.SILLAS_TOTAL || 2000);
const SILLAS_POR_SALVA = Number(process.env.SILLAS_POR_SALVA || 2);
const USUARIOS = 200; // prueba001 ... prueba200

let contadorUsuarios = 0;
let contadorSillas = 0;
let primeraSalva = null;

// Reparte los usuarios de prueba en orden: prueba001, prueba002, ...
function asignarUsuario(context, events, done) {
  const n = (contadorUsuarios++ % USUARIOS) + 1;
  context.vars.email = `prueba${String(n).padStart(3, '0')}@taquilla.test`;
  return done();
}

// Espera hasta el siguiente múltiplo de PERIODO_MS (reloj de pared) y anota el número de salva.
function esperarSalva(context, events, done) {
  const espera = PERIODO_MS - (Date.now() % PERIODO_MS);
  setTimeout(() => {
    context.vars.salva = Math.floor(Date.now() / PERIODO_MS);
    if (primeraSalva === null) primeraSalva = context.vars.salva;
    return done();
  }, espera + 5);
}

// Variante "distintas": cada usuario reserva una silla que nadie más intenta.
function sillaDistinta(context, events, done) {
  const i = contadorSillas++;
  if (i >= SILLAS_TOTAL) events.emit('counter', 'concurrencia.sillas_agotadas', 1);
  context.vars.silla = SILLA_BASE + (i % SILLAS_TOTAL);
  return done();
}

// Variante "mismas": en cada salva, todos los usuarios se disputan las mismas SILLAS_POR_SALVA sillas.
// Cada salva usa sillas nuevas, para que haya competencia real en todas y no solo en la primera.
function sillaCompartida(context, events, done) {
  const oleada = context.vars.salva - primeraSalva;
  const i = oleada * SILLAS_POR_SALVA + Math.floor(Math.random() * SILLAS_POR_SALVA);
  if (i >= SILLAS_TOTAL) events.emit('counter', 'concurrencia.sillas_agotadas', 1);
  context.vars.silla = SILLA_BASE + (i % SILLAS_TOTAL);
  return done();
}

// Clasifica cada respuesta de reserva: éxito, conflicto esperado de negocio (409) o error interno (5xx).
function clasificarReserva(req, res, context, events, next) {
  const c = res.statusCode;
  let metrica;
  if (c === 201) metrica = 'reserva.exito_201';
  else if (c === 409) metrica = 'reserva.conflicto_409';
  else if (c >= 500) metrica = 'reserva.error_5xx';
  else metrica = `reserva.otro_${c}`; // 401, 403, 404...
  events.emit('counter', metrica, 1);
  return next();
}

module.exports = { asignarUsuario, esperarSalva, sillaDistinta, sillaCompartida, clasificarReserva };