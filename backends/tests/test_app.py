import json

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


# Estas dos no necesitan base de datos: la validación ocurre antes de consultarla

def test_purchase_without_email_returns_400(client):
    response = client.post(
        "/api/events/1/seats/1/purchase",
        json={"buyer_name": "Ana Pérez"},
    )

    assert response.status_code == 400
    assert "buyer_email" in response.get_json()["message"]


def test_purchase_with_invalid_email_returns_400(client):
    response = client.post(
        "/api/events/1/seats/1/purchase",
        json={"buyer_name": "Ana Pérez", "buyer_email": "ana@correo"},
    )

    assert response.status_code == 400


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
