import os

import pytest

# Todas las pruebas de este archivo usan una base PostgreSQL real.
# Sin TEST_DATABASE_URL se saltan (ver README, sección 6.8, para crear una base de prueba).
pytestmark = pytest.mark.skipif(
    not os.getenv("TEST_DATABASE_URL"),
    reason="TEST_DATABASE_URL no está definida: se saltan las pruebas con base de datos",
)

BUYER = {"buyer_name": "Ana Pérez", "buyer_email": "ana@example.com"}

# Ids fijos del seed (db/init/02_seed.sql): el concierto es el evento 1 con las sillas 1 a 2000,
# y la silla 2001 es del evento 2.
CONCERT_ID = 1
CONCERT_SEAT_ID = 1
OTHER_EVENT_SEAT_ID = 2001


def test_index_page_shows_events(client, database):
    response = client.get("/")

    assert response.status_code == 200
    assert response.mimetype == "text/html"
    assert "Concierto Caña y Clave - Venta flash" in response.get_data(as_text=True)


def test_event_page_shows_seats(client, database):
    response = client.get(f"/events/{CONCERT_ID}")

    assert response.status_code == 200
    assert f'data-seat-id="{CONCERT_SEAT_ID}"' in response.get_data(as_text=True)
    assert client.get("/events/999").status_code == 404


def test_events_list_has_seed_data(client, database):
    response = client.get("/api/events")

    assert response.status_code == 200
    events = response.get_json()
    assert len(events) == 3
    concert = next(event for event in events if event["id"] == CONCERT_ID)
    assert concert["name"] == "Concierto Caña y Clave - Venta flash"
    assert concert["available_seats"] == 2000
    assert concert["total_seats"] == 2000


def test_unknown_event_returns_404(client, database):
    assert client.get("/api/events/999").status_code == 404
    assert client.get("/api/events/999/seats").status_code == 404


def test_seats_list_does_not_show_buyer_data(client, database):
    response = client.get(f"/api/events/{CONCERT_ID}/seats")

    assert response.status_code == 200
    seats = response.get_json()
    assert len(seats) == 2000
    assert "buyer_email" not in seats[0]


def test_purchase_available_seat_returns_201(client, database):
    response = client.post(f"/api/events/{CONCERT_ID}/seats/{CONCERT_SEAT_ID}/purchase", json=BUYER)

    assert response.status_code == 201
    seat = response.get_json()
    assert seat["id"] == CONCERT_SEAT_ID
    assert seat["status"] == "sold"

    event = client.get(f"/api/events/{CONCERT_ID}").get_json()
    assert event["available_seats"] == 1999


def test_purchase_same_seat_twice_returns_409(client, database):
    url = f"/api/events/{CONCERT_ID}/seats/{CONCERT_SEAT_ID}/purchase"
    client.post(url, json=BUYER)

    response = client.post(url, json={"buyer_name": "Otro comprador", "buyer_email": "otro@example.com"})

    assert response.status_code == 409


def test_purchase_seat_from_other_event_returns_404(client, database):
    response = client.post(f"/api/events/{CONCERT_ID}/seats/{OTHER_EVENT_SEAT_ID}/purchase", json=BUYER)

    assert response.status_code == 404
