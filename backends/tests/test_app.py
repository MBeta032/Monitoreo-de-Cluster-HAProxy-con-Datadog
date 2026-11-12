import json


def test_health_returns_200(client):
    response = client.get("/health")

    assert response.status_code == 200


def test_index_returns_instance_name(client):
    response = client.get("/")

    assert response.status_code == 200
    assert "instance" in response.get_json()


def test_error_returns_500_and_logs_error_level(client, log_stream):
    response = client.get("/error")

    assert response.status_code == 500
    last_line = log_stream.getvalue().splitlines()[-1]
    log_record = json.loads(last_line)
    assert log_record["level"] == "ERROR"
    assert log_record["path"] == "/error"


def test_index_request_is_counted_in_metrics(client):
    client.get("/")

    metrics_text = client.get("/metrics").get_data(as_text=True)
    assert 'http_requests_total{handler="/",method="GET",status="200"}' in metrics_text


def test_health_is_not_counted_in_metrics(client):
    client.get("/health")

    metrics_text = client.get("/metrics").get_data(as_text=True)
    assert 'handler="/health"' not in metrics_text


def test_unknown_route_uses_unmatched_handler(client):
    response = client.get("/no-existe")

    assert response.status_code == 404
    metrics_text = client.get("/metrics").get_data(as_text=True)
    assert 'http_requests_total{handler="unmatched",method="GET",status="404"}' in metrics_text
