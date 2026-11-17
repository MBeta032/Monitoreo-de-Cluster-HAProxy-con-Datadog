'use strict';

// No imprimir credenciales, cookies ni cuerpos de respuesta.
function body(response) {
  if (typeof response.body === 'object' && response.body !== null && !Buffer.isBuffer(response.body)) return response.body;
  return JSON.parse(String(response.body));
}
function check(response, events, operation, status) {
  if (response.statusCode !== status) {
    events.emit('counter', `jj.${operation}.http_${response.statusCode}`, 1);
    throw new Error(`JJ_${operation}_HTTP_${response.statusCode}`);
  }
  return body(response);
}
module.exports = {
  async iniciar(context) {
    const { JJ_EMAIL, JJ_PASSWORD, JJ_EVENT_ID = '1', JJ_OPERACION = 'consulta' } = process.env;
    if (!JJ_EMAIL || !JJ_PASSWORD) throw new Error('JJ_CREDENCIALES_AUSENTES');
    if (!/^\d+$/.test(JJ_EVENT_ID)) throw new Error('JJ_EVENTO_INVALIDO');
    context.vars.email = JJ_EMAIL;
    context.vars.password = JJ_PASSWORD;
    context.vars.event_id = Number(JJ_EVENT_ID);
    context.vars.operacion = JJ_OPERACION;
  },
  async login(request, response, context, events) {
    const data = check(response, events, 'login', 200);
    if (!data.user || !Number.isInteger(data.user.id) || typeof data.csrf_token !== 'string' || !data.csrf_token) {
      throw new Error('JJ_LOGIN_CONTRATO_INVALIDO');
    }
    context.vars.csrf_token = data.csrf_token;
    context.vars.user_id = data.user.id;
    events.emit('counter', 'jj.login_ok', 1);
  },
  async eventos(request, response, context, events) {
    const data = check(response, events, 'eventos', 200);
    if (!Array.isArray(data) || !data.some(x => x.id === context.vars.event_id)) {
      throw new Error('JJ_EVENTO_NO_ENCONTRADO');
    }
  },
  async sillas(request, response, context, events) {
    const data = check(response, events, 'sillas', 200);
    if (!Array.isArray(data)) throw new Error('JJ_SILLAS_CONTRATO_INVALIDO');
    if (context.vars.operacion === 'reserva') {
      const free = data.filter(x => x.status === 'available' && Number.isInteger(x.id));
      if (!free.length) {
        events.emit('counter', 'jj.sin_cupos', 1);
        throw new Error('JJ_SIN_SILLAS_DISPONIBLES');
      }
      context.vars.seat_id = free[Math.floor(Math.random() * free.length)].id;
    }
  },
  async reserva(request, response, context, events) {
    if (response.statusCode === 409) events.emit('counter', 'jj.conflicto_409', 1);
    const data = check(response, events, 'reserva', 201);
    if (!Number.isInteger(data.id) || typeof data.code !== 'string') throw new Error('JJ_RESERVA_CONTRATO_INVALIDO');
    context.vars.reservation_id = data.id;
    events.emit('counter', 'jj.reserva_ok', 1);
  },
  async misReservas(request, response, context, events) {
    const data = check(response, events, 'mis_reservas', 200);
    if (!Array.isArray(data)) throw new Error('JJ_LISTA_RESERVAS_INVALIDA');
    if (context.vars.operacion === 'reserva' && !data.some(x => x.id === context.vars.reservation_id)) {
      throw new Error('JJ_RESERVA_NO_VISIBLE_EN_SESION');
    }
    events.emit('counter', 'jj.flujo_ok', 1);
  },
};
