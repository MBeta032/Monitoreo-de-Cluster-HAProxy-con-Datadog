import os

import pytest

# Pruebas de la cartelera, el plano de zonas y las sillas, con una base PostgreSQL real.
# Sin TEST_DATABASE_URL se saltan (ver README, sección 6.8, para crear una base de prueba).
pytestmark = pytest.mark.skipif(
    not os.getenv("TEST_DATABASE_URL"),
    reason="TEST_DATABASE_URL no está definida: se saltan las pruebas con base de datos",
)

# Ids fijos del seed (db/init/02_seed.sql):
# - Concierto (evento 1): Platea 1-500, Gradería Central 501-1000, Izquierda 1001-1500, Derecha 1501-2000.
# - Obra de teatro (evento 2): una sola zona, sillas 2001-2100.
# - Cuentos de medianoche (evento 4): una sola zona, 40 sillas, todas reservadas
#   (una por usuario, de prueba161 a prueba200).
CONCERT_ID = 1
THEATER_ID = 2
SOLD_OUT_EVENT_ID = 4


def test_index_page_shows_events(client, database):
    response = client.get("/")

    assert response.status_code == 200
    assert response.mimetype == "text/html"
    page = response.get_data(as_text=True)
    assert "Concierto Caña y Clave" in page
    assert "AGOTADO" in page


def test_events_list_has_seed_data(client, database):
    response = client.get("/api/events")

    assert response.status_code == 200
    events = {event["id"]: event for event in response.get_json()}
    assert len(events) == 4
    assert events[CONCERT_ID]["name"] == "Concierto Caña y Clave"
    assert events[CONCERT_ID]["category"] == "Concierto"
    assert events[CONCERT_ID]["is_flash_sale"] is True
    assert events[CONCERT_ID]["available_seats"] == 2000
    assert events[SOLD_OUT_EVENT_ID]["available_seats"] == 0


def test_unknown_event_returns_404(client, database):
    assert client.get("/events/999").status_code == 404
    assert client.get("/api/events/999").status_code == 404
    assert client.get("/api/events/999/seats").status_code == 404


def test_event_with_many_zones_shows_the_zone_map(client, database):
    page = client.get(f"/events/{CONCERT_ID}").get_data(as_text=True)

    for zone in ["Platea", "Gradería Central", "Gradería Izquierda", "Gradería Derecha"]:
        assert zone in page
    assert "section=Platea" in page
    # En el plano todavía no hay sillas
    assert "data-seat-id" not in page


def test_section_parameter_shows_only_that_zone(client, database):
    page = client.get(f"/events/{CONCERT_ID}?section=Platea").get_data(as_text=True)

    assert 'data-seat-id="1"' in page
    assert 'data-seat-id="500"' in page
    # La silla 501 es de Gradería Central: no debe aparecer
    assert 'data-seat-id="501"' not in page


def test_unknown_section_returns_404(client, database):
    assert client.get(f"/events/{CONCERT_ID}?section=NoExiste").status_code == 404
    assert client.get(f"/api/events/{CONCERT_ID}/seats?section=NoExiste").status_code == 404


def test_event_with_one_zone_shows_seats_directly(client, database):
    page = client.get(f"/events/{THEATER_ID}").get_data(as_text=True)

    assert 'data-seat-id="2001"' in page


def test_full_zone_shows_sold_out_in_the_map(client, database, test_pool):
    # Se ocupan todas las sillas de Gradería Derecha directamente en la base de prueba
    with test_pool.connection() as conn:
        conn.execute(
            "UPDATE seats SET status = 'reserved' WHERE event_id = %s AND section = 'Gradería Derecha'",
            (CONCERT_ID,),
        )

    page = client.get(f"/events/{CONCERT_ID}").get_data(as_text=True)

    assert "AGOTADO" in page
    # La zona llena ya no es un enlace que se pueda escoger
    assert "section=Grader%C3%ADa+Derecha" not in page
    assert "section=Grader%C3%ADa+Central" in page


def test_api_seats_can_be_filtered_by_section(client, database):
    response = client.get(f"/api/events/{CONCERT_ID}/seats?section=Gradería Central")

    assert response.status_code == 200
    seats = response.get_json()
    assert len(seats) == 500
    assert all(seat["section"] == "Gradería Central" for seat in seats)
    assert len(client.get(f"/api/events/{CONCERT_ID}/seats").get_json()) == 2000


def test_listing_shows_last_seats_when_less_than_10_percent(client, database, test_pool):
    # Se ocupan 95 de las 100 sillas de la obra de teatro: quedan 5 (menos del 10 %)
    with test_pool.connection() as conn:
        conn.execute(
            "UPDATE seats SET status = 'reserved' WHERE event_id = %s AND id <= 2095",
            (THEATER_ID,),
        )

    page = client.get("/").get_data(as_text=True)

    assert "Últimas 5 sillas" in page
