module.exports = {
  capturarCookie
};

async function capturarCookie(requestParams, response, context) {
  const setCookie = response.headers["set-cookie"];
  const cookie = Array.isArray(setCookie) ? setCookie[0] : setCookie;

  if (!cookie) {
    throw new Error("El login no devolvió la cookie de sesión");
  }

  context.vars.sessionCookie = cookie.split(";")[0];
}
