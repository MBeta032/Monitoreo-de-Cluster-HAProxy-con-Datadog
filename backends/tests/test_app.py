import json

import pytest

import auth
import db


def test_health_returns_200(client):
    response = client.get("/health")

    assert response.status_code == 200


def test_api_info_returns_instance_name(client):
    response = client.get("/api/info")

    assert response.status_code == 200
    assert "instance" in response.get_json()


def test_error_returns_500_and_logs_error_level(client, log_stream):
    response = client.get("/error")

    assert response.status_code == 500
    last_line = log_stream.getvalue().splitlines()[-1]
    log_record = json.loads(last_line)
    assert log_record["level"] == "ERROR"
    assert log_record["path"] == "/error"


def test_api_info_request_is_counted_in_metrics(client):
    client.get("/api/info")

    metrics_text = client.get("/metrics").get_data(as_text=True)
    assert 'http_requests_total{handler="/api/info",method="GET",status="200"}' in metrics_text


def test_health_is_not_counted_in_metrics(client):
    client.get("/health")

    metrics_text = client.get("/metrics").get_data(as_text=True)
    assert 'handler="/health"' not in metrics_text


def test_unknown_route_uses_unmatched_handler(client):
    response = client.get("/no-existe")

    assert response.status_code == 404
    metrics_text = client.get("/metrics").get_data(as_text=True)
    assert 'http_requests_total{handler="unmatched",method="GET",status="404"}' in metrics_text


# Estas no necesitan base de datos: sin sesión la API responde 401 antes de consultarla

def test_reserve_without_session_returns_401(client):
    response = client.post("/api/events/1/seats/1/reserve")

    assert response.status_code == 401


def test_my_reservations_api_without_session_returns_401(client):
    response = client.get("/api/reservations")

    assert response.status_code == 401


def test_confirm_page_without_session_redirects_to_login_with_next(client):
    response = client.get("/events/1/confirm?seat=5")

    assert response.status_code == 302
    location = response.headers["Location"]
    assert location.startswith("/login?")
    assert "next=/events/1/confirm?seat%3D5" in location


def test_confirm_post_without_session_redirects_to_login_with_seat(client):
    # La sesión venció mientras la página Confirmar estaba abierta: sin sesión tampoco hay
    # token CSRF, así que se espera la redirección a /login (no un 403) y que next lleve la silla.
    response = client.post("/events/1/confirm", data={"seat_id": 5, "csrf_token": "token-viejo"})

    assert response.status_code == 302
    location = response.headers["Location"]
    assert location.startswith("/login?")
    assert "next=/events/1/confirm?seat%3D5" in location


def test_database_down_returns_503_and_logs_error(client, log_stream, unreachable_database):
    response = client.get("/api/events")

    assert response.status_code == 503
    assert response.get_json()["error"] == "Service Unavailable"

    last_line = log_stream.getvalue().splitlines()[-1]
    log_record = json.loads(last_line)
    assert log_record["level"] == "ERROR"
    assert log_record["status_code"] == 503

    metrics_text = client.get("/metrics").get_data(as_text=True)
    assert 'http_requests_total{handler="/api/events",method="GET",status="503"}' in metrics_text


def test_index_page_with_database_down_returns_503_html(client, log_stream, unreachable_database):
    response = client.get("/")

    assert response.status_code == 503
    assert response.mimetype == "text/html"
    assert "Servicio no disponible" in response.get_data(as_text=True)

    last_line = log_stream.getvalue().splitlines()[-1]
    log_record = json.loads(last_line)
    assert log_record["level"] == "ERROR"
    assert log_record["status_code"] == 503


def test_unhandled_exception_is_counted_and_logged_as_error(client, log_stream, monkeypatch):
    # Una ruta que lanza una excepción no manejada: Flask responde 500 y aun así
    # ejecuta after_request, así que la petición queda en el log y en las métricas.
    def broken_list_events():
        raise RuntimeError("fallo inesperado de prueba")

    monkeypatch.setattr(db, "list_events", broken_list_events)

    response = client.get("/api/events")

    assert response.status_code == 500

    last_line = log_stream.getvalue().splitlines()[-1]
    log_record = json.loads(last_line)
    assert log_record["level"] == "ERROR"
    assert log_record["path"] == "/api/events"

    metrics_text = client.get("/metrics").get_data(as_text=True)
    assert 'http_requests_total{handler="/api/events",method="GET",status="500"}' in metrics_text


# Sesiones y CSRF: estas no necesitan base de datos (el token se revisa antes de consultarla)

def test_post_login_without_csrf_token_returns_403(client):
    response = client.post("/login", data={"email": "prueba001@taquilla.test", "password": "x"})

    assert response.status_code == 403


def test_api_logout_without_csrf_header_returns_403(client):
    response = client.post("/api/logout")

    assert response.status_code == 403


@pytest.mark.parametrize("url", ["/events/1", "/events/1?section=Platea", "/"])
def test_internal_next_is_accepted(url):
    assert auth.is_safe_next(url)


@pytest.mark.parametrize("url", [
    "https://otro.sitio",
    "//otro.sitio",
    "/\\otro.sitio",
    "/\t/otro.sitio",
    "/\n/otro.sitio",
    "/\r/otro.sitio",
    "javascript:alert(1)",
    "",
])
def test_external_next_is_rejected(url):
    assert not auth.is_safe_next(url)


# Páginas de error: las páginas web tienen el estilo del sitio; la API responde JSON

def test_unknown_page_shows_styled_404_with_link_to_listing(client):
    response = client.get("/no-existe")

    assert response.status_code == 404
    assert response.mimetype == "text/html"
    page = response.get_data(as_text=True)
    assert "Taquilla Sucursal" in page
    assert "Volver a la cartelera" in page


def test_unknown_api_route_returns_json_404(client):
    response = client.get("/api/no-existe")

    assert response.status_code == 404
    assert response.get_json()["error"] == "Not Found"
