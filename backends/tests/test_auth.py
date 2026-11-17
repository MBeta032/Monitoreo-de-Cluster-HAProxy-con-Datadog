import os

import pytest

import app as backend_app
from conftest import TEST_PASSWORD, csrf_token_for

# Pruebas de cuentas y sesiones con una base PostgreSQL real.
# Sin TEST_DATABASE_URL se saltan (ver README, sección 6.8, para crear una base de prueba).
pytestmark = pytest.mark.skipif(
    not os.getenv("TEST_DATABASE_URL"),
    reason="TEST_DATABASE_URL no está definida: se saltan las pruebas con base de datos",
)

SEED_EMAIL = "prueba001@taquilla.test"
SEED_NAME = "Prueba 001"


def login_with_form(test_client, email, password, next_url=""):
    return test_client.post("/login", data={
        "csrf_token": csrf_token_for(test_client),
        "email": email,
        "password": password,
        "next": next_url,
    })


def test_register_creates_account_and_starts_session(client, database):
    response = client.post("/register", data={
        "csrf_token": csrf_token_for(client),
        "name": "Ana Pérez",
        "email": "Ana@Example.com",
        "password": "una-clave-segura",
    })

    assert response.status_code == 302
    with client.session_transaction() as test_session:
        assert "user_id" in test_session
    # El correo se guarda en minúsculas: se puede iniciar sesión escribiéndolo distinto
    assert login_with_form(client, "ana@example.com", "una-clave-segura").status_code == 302


def test_register_with_existing_email_is_rejected(client, database):
    response = client.post("/register", data={
        "csrf_token": csrf_token_for(client),
        "name": "Otra persona",
        "email": SEED_EMAIL.upper(),
        "password": "una-clave-segura",
    })

    assert response.status_code == 409
    assert "Ya existe una cuenta con ese correo" in response.get_data(as_text=True)


def test_login_with_correct_password(client, database):
    response = login_with_form(client, SEED_EMAIL, TEST_PASSWORD)

    assert response.status_code == 302
    assert response.headers["Location"] == "/"
    assert SEED_NAME in client.get("/").get_data(as_text=True)


def test_login_with_wrong_password(client, database):
    response = login_with_form(client, SEED_EMAIL, "clave-equivocada")

    assert response.status_code == 401
    assert "Correo o contraseña incorrectos" in response.get_data(as_text=True)
    with client.session_transaction() as test_session:
        assert "user_id" not in test_session


def test_login_keeps_internal_next(client, database):
    response = login_with_form(client, SEED_EMAIL, TEST_PASSWORD, next_url="/events/2")

    assert response.headers["Location"] == "/events/2"


@pytest.mark.parametrize("external_url", ["https://otro.sitio/robar", "//otro.sitio/robar", "/\t/otro.sitio"])
def test_login_rejects_external_next(client, database, external_url):
    response = login_with_form(client, SEED_EMAIL, TEST_PASSWORD, next_url=external_url)

    assert response.status_code == 302
    assert response.headers["Location"] == "/"


def test_api_login_returns_user_and_csrf_token(client, database):
    response = client.post("/api/login", json={"email": SEED_EMAIL, "password": TEST_PASSWORD})

    assert response.status_code == 200
    data = response.get_json()
    assert data["user"]["email"] == SEED_EMAIL
    assert data["csrf_token"] != ""
    assert "password_hash" not in data["user"]


def test_api_login_with_wrong_password_returns_401(client, database):
    response = client.post("/api/login", json={"email": SEED_EMAIL, "password": "clave-equivocada"})

    assert response.status_code == 401


def test_api_logout_needs_csrf_header(client, database):
    login = client.post("/api/login", json={"email": SEED_EMAIL, "password": TEST_PASSWORD})
    csrf_token = login.get_json()["csrf_token"]

    assert client.post("/api/logout").status_code == 403
    assert client.post("/api/logout", headers={"X-CSRF-Token": csrf_token}).status_code == 200


def test_session_works_in_another_instance_with_same_secret_key(client, database):
    # Simula dos backends: el cliente A inicia sesión ("backend1") y el cliente B ("backend2")
    # recibe la misma cookie. Como los dos usan la misma SECRET_KEY, B reconoce la sesión.
    client.post("/api/login", json={"email": SEED_EMAIL, "password": TEST_PASSWORD})
    session_cookie = client.get_cookie("session")

    other_client = backend_app.app.test_client()
    other_client.set_cookie("session", session_cookie.value)

    assert SEED_NAME in other_client.get("/").get_data(as_text=True)


def test_session_is_rejected_with_a_different_secret_key(client, database, monkeypatch):
    # Si otro backend tuviera una SECRET_KEY distinta, no podría leer la cookie: el usuario
    # perdería la sesión al cambiar de backend. Por eso la clave es la misma en los 3.
    client.post("/api/login", json={"email": SEED_EMAIL, "password": TEST_PASSWORD})
    session_cookie = client.get_cookie("session")

    monkeypatch.setitem(backend_app.app.config, "SECRET_KEY", "otra-clave-distinta")
    other_client = backend_app.app.test_client()
    other_client.set_cookie("session", session_cookie.value)

    page = other_client.get("/").get_data(as_text=True)
    assert SEED_NAME not in page
    assert "Iniciar sesión" in page
