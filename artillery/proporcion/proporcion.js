async function asignarSilla(context) {
  const respuesta = await fetch(
    "http://haproxy:8080/api/events/1/seats"
  );

  if (!respuesta.ok) {
    throw new Error("No se pudieron consultar los asientos");
  }

  const asientos = await respuesta.json();

  const disponibles = asientos.filter(
    (asiento) => asiento.status === "available"
  );

  if (disponibles.length === 0) {
    throw new Error("No hay asientos disponibles");
  }

  const indice = Math.floor(Math.random() * disponibles.length);

  context.vars.seatId = disponibles[indice].id;
}

module.exports = {
  asignarSilla
};
