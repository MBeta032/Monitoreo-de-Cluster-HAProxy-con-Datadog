import os

from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool

# Una conexión por cada hilo del worker. Mismo valor por defecto que gunicorn.conf.py.
POOL_SIZE = int(os.getenv("GUNICORN_THREADS", "4"))

# Segundos que una petición espera por una conexión libre. Después el pool lanza
# PoolTimeout y la app responde 503 (ver app.py).
POOL_TIMEOUT_SECONDS = 5

# conninfo vacío: libpq toma los datos de conexión de sus variables estándar
# PGHOST, PGPORT, PGDATABASE, PGUSER y PGPASSWORD (definidas en docker-compose.yml).
# El pool se crea cerrado: cada worker de Gunicorn lo abre después del fork (gunicorn.conf.py).
pool = ConnectionPool(
    conninfo="",
    min_size=POOL_SIZE,
    max_size=POOL_SIZE,
    timeout=POOL_TIMEOUT_SECONDS,
    # Antes de entregar una conexión revisa que siga viva (por ejemplo, después de reiniciar db)
    check=ConnectionPool.check_connection,
    open=False,
)


def list_events():
    # Eventos con el total de sillas y cuántas quedan libres
    with pool.connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                """
                SELECT events.id, events.name, events.venue, events.starts_at,
                       count(seats.id) FILTER (WHERE seats.status = 'available') AS available_seats,
                       count(seats.id) AS total_seats
                FROM events
                LEFT JOIN seats ON seats.event_id = events.id
                GROUP BY events.id
                ORDER BY events.starts_at
                """
            )
            return cur.fetchall()


def get_event(event_id):
    # Un evento con sus sillas libres, o None si no existe
    with pool.connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                """
                SELECT events.id, events.name, events.venue, events.starts_at,
                       count(seats.id) FILTER (WHERE seats.status = 'available') AS available_seats,
                       count(seats.id) AS total_seats
                FROM events
                LEFT JOIN seats ON seats.event_id = events.id
                WHERE events.id = %s
                GROUP BY events.id
                """,
                (event_id,),
            )
            return cur.fetchone()


def list_seats(event_id):
    # Sillas del evento con su estado. No incluye los datos del comprador: esta lista es pública.
    with pool.connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                """
                SELECT id, section, seat_row, seat_number, status
                FROM seats
                WHERE event_id = %s
                ORDER BY id
                """,
                (event_id,),
            )
            return cur.fetchall()


def purchase_seat(event_id, seat_id, buyer_name, buyer_email):
    # Vende la silla en una sola consulta, solo si sigue libre.
    # Si dos compradores llegan al tiempo, PostgreSQL hace esperar al segundo; cuando el
    # primero termina, la silla ya no está 'available' y el segundo no actualiza nada.
    # Devuelve la silla vendida, o None si no se pudo vender (no existe o ya estaba vendida).
    with pool.connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                """
                UPDATE seats
                SET status = 'sold', buyer_name = %s, buyer_email = %s, sold_at = now()
                WHERE id = %s AND event_id = %s AND status = 'available'
                RETURNING id, event_id, section, seat_row, seat_number, status, sold_at
                """,
                (buyer_name, buyer_email, seat_id, event_id),
            )
            return cur.fetchone()


def seat_exists(event_id, seat_id):
    # Sirve para distinguir entre "la silla no existe en este evento" (404) y "ya fue vendida" (409)
    with pool.connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT 1 FROM seats WHERE id = %s AND event_id = %s",
                (seat_id, event_id),
            )
            return cur.fetchone() is not None
