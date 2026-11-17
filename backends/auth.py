import secrets
from functools import wraps

from flask import g, redirect, request, session, url_for
from werkzeug.security import check_password_hash, generate_password_hash

import db

# pbkdf2 con 600.000 iteraciones: el mínimo que recomienda OWASP para PBKDF2-HMAC-SHA256.
# No se usa scrypt (el método por defecto de Werkzeug) porque pide 32 MiB por cada hash:
# con 16 inicios de sesión al tiempo un backend pasaría su límite de 384 MB (README, sección 6).
PASSWORD_HASH_METHOD = "pbkdf2:sha256:600000"

MIN_PASSWORD_LENGTH = 8


def hash_password(password):
    return generate_password_hash(password, method=PASSWORD_HASH_METHOD)


def password_matches(password_hash, password):
    return check_password_hash(password_hash, password)


def start_session(user_id):
    # Sesión nueva al iniciar sesión: se borra lo anterior para no reutilizar una sesión vieja.
    # En la cookie solo van el id del usuario y el token CSRF (nada de datos personales).
    session.clear()
    session.permanent = True
    session["user_id"] = user_id
    session["csrf_token"] = secrets.token_urlsafe(32)


def get_current_user():
    # Busca al usuario de la sesión una sola vez por petición y lo guarda en g.
    # Si la cuenta ya no existe (por ejemplo, se recreó la base), se trata como sin sesión.
    if "user" not in g:
        user_id = session.get("user_id")
        if user_id is None:
            g.user = None
        else:
            g.user = db.get_user(user_id)
    return g.user


def get_csrf_token():
    # Un token por sesión. Se crea la primera vez que un formulario lo necesita.
    if "csrf_token" not in session:
        session["csrf_token"] = secrets.token_urlsafe(32)
    return session["csrf_token"]


def csrf_token_is_valid(token):
    # Compara el token recibido (campo oculto o encabezado X-CSRF-Token) con el de la sesión
    expected_token = session.get("csrf_token")
    if not expected_token or not token:
        return False
    return secrets.compare_digest(expected_token, token)


def is_safe_next(url):
    # Solo se aceptan rutas internas como "/events/1".
    # Se rechazan "https://otro.sitio" y "//otro.sitio" (redirecciones abiertas).
    if not url or not url.startswith("/"):
        return False
    # Sin caracteres de control: los navegadores y Werkzeug ignoran tabs y saltos de línea
    # dentro de una URL, así que "/\t/otro.sitio" termina siendo "//otro.sitio".
    for character in url:
        if ord(character) < 32 or ord(character) == 127:
            return False
    if url.startswith("//") or url.startswith("/\\"):
        return False
    return True


def login_required(view):
    # Decorador para páginas que necesitan sesión (como en el tutorial oficial de Flask).
    # Sin sesión, redirige a /login y guarda en next la página que se quería ver.
    @wraps(view)
    def wrapped_view(**kwargs):
        if get_current_user() is None:
            if request.query_string:
                next_url = request.full_path
            else:
                next_url = request.path
            return redirect(url_for("login", next=next_url))
        return view(**kwargs)

    return wrapped_view
