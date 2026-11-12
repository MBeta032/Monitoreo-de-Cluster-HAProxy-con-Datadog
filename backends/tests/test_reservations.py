import os

import pytest

import app as backend_app
from conftest import TEST_PASSWORD, csrf_token_for

# Pruebas del flujo de reserva (API y páginas) con una base PostgreSQL real.
# Sin TEST_DATABASE_URL se saltan (ver README, sección 6.8, para crear una base de prueba).
pytestmark = pytest.mark.skipif(
    not os.getenv("TEST_DATABASE_URL"),
    reason="TEST_DATABASE_URL no está definida: se saltan las pruebas con base de datos",
)

# Ids fijos del seed: el concierto es el evento 1 (sillas 1 a 2000) y la silla 2001 es del evento 2.
# La silla 2201 es de Cuentos de medianoche (evento 4) y ya está reservada por prueba161.
CONCERT_ID = 1
OTHER_EVENT_SEAT_ID = 2001
SOLD_OUT_EVENT_ID = 4
TAKEN_SEAT_ID = 2201


def api_login(test_client, email):
    # Inicia sesión por la API y devuelve el token CSRF para los POST siguientes
    response = test_client.post("/api/login", json={"email": email, "password": TEST_PASSWORD})
    assert response.status_code == 200
    return response.get_json()["csrf_token"]


def api_reserve(test_client, csrf_token, seat_id, event_id=CONCERT_ID):
    return test_client.post(
        f"/api/events/{event_id}/seats/{seat_id}/reserve",
        headers={"X-CSRF-Token": csrf_token},
    )


def test_reserve_with_api_returns_201_and_code(client, database):
    csrf_token = api_login(client, "prueba001@taquilla.test")

    response = api_reserve(client, csrf_token, seat_id=1)

    assert response.status_code == 201
    reservation = response.get_json()
    assert reservation["seat_id"] == 1
    assert reservation["section"] == "Platea"
    # "TS-" más el id con 6 dígitos
    assert reservation["code"] == f"TS-{reservation['id']:06d}"

    event = client.get(f"/api/events/{CONCERT_ID}").get_json()
    assert event["available_seats"] == 1999


def test_same_seat_twice_returns_409(client, database):
    first_token = api_login(client, "prueba001@taquilla.test")
    api_reserve(client, first_token, seat_id=1)

    other_client = backend_app.app.test_client()
    other_token = api_login(other_client, "prueba002@taquilla.test")
    response = api_reserve(other_client, other_token, seat_id=1)

    assert response.status_code == 409


def test_reserve_without_csrf_header_returns_403(client, database):
    api_login(client, "prueba001@taquilla.test")

    response = client.post(f"/api/events/{CONCERT_ID}/seats/1/reserve")

    assert response.status_code == 403


def test_reserve_seat_from_other_event_returns_404(client, database):
    csrf_token = api_login(client, "prueba001@taquilla.test")

    response = api_reserve(client, csrf_token, seat_id=OTHER_EVENT_SEAT_ID)

    assert response.status_code == 404


def test_confirm_page_reserves_and_redirects_with_303(client, database):
    api_login(client, "prueba001@taquilla.test")
    assert client.get(f"/events/{CONCERT_ID}/confirm?seat=5").status_code == 200

    response = client.post(f"/events/{CONCERT_ID}/confirm", data={
        "csrf_token": csrf_token_for(client),
        "seat_id": 5,
    })

    # POST/Redirect/GET: la pantalla Listo se pide con GET
    assert response.status_code == 303
    done_url = response.headers["Location"]
    assert done_url.startswith("/reservations/")
    done_page = client.get(done_url).get_data(as_text=True)
    assert "¡Reserva confirmada!" in done_page
    assert "TS-" in done_page


def test_confirm_page_with_taken_seat_shows_warning(client, database):
    api_login(client, "prueba001@taquilla.test")

    page = client.get(f"/events/{SOLD_OUT_EVENT_ID}/confirm?seat={TAKEN_SEAT_ID}")
    assert page.status_code == 200
    assert "antes que tú" in page.get_data(as_text=True)

    response = client.post(f"/events/{SOLD_OUT_EVENT_ID}/confirm", data={
        "csrf_token": csrf_token_for(client),
        "seat_id": TAKEN_SEAT_ID,
    })
    assert response.status_code == 409
    assert "antes que tú" in response.get_data(as_text=True)


def test_confirm_post_without_csrf_returns_403(client, database):
    api_login(client, "prueba001@taquilla.test")

    response = client.post(f"/events/{CONCERT_ID}/confirm", data={"seat_id": 5})

    assert response.status_code == 403


def test_my_reservations_show_only_my_own(client, database):
    first_token = api_login(client, "prueba001@taquilla.test")
    first_code = api_reserve(client, first_token, seat_id=1).get_json()["code"]

    other_client = backend_app.app.test_client()
    other_token = api_login(other_client, "prueba002@taquilla.test")
    other_code = api_reserve(other_client, other_token, seat_id=2).get_json()["code"]

    page = other_client.get("/reservations").get_data(as_text=True)
    assert other_code in page
    assert first_code not in page

    api_reservations = other_client.get("/api/reservations").get_json()
    assert [reservation["code"] for reservation in api_reservations] == [other_code]


def test_reservation_of_another_user_returns_404(client, database):
    first_token = api_login(client, "prueba001@taquilla.test")
    reservation_id = api_reserve(client, first_token, seat_id=1).get_json()["id"]
    assert client.get(f"/reservations/{reservation_id}").status_code == 200

    other_client = backend_app.app.test_client()
    api_login(other_client, "prueba002@taquilla.test")

    assert other_client.get(f"/reservations/{reservation_id}").status_code == 404


def test_empty_reservations_page(client, database):
    api_login(client, "prueba003@taquilla.test")

    page = client.get("/reservations").get_data(as_text=True)

    assert "Aún no tienes reservas" in page
