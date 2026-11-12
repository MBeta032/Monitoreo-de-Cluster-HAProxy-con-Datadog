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


def create_user(name, email, password_hash):
    # Devuelve el id del usuario nuevo, o None si ya existe una cuenta con ese correo.
    # ON CONFLICT evita el error aunque dos personas se registren con el mismo correo al tiempo.
    with pool.connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO users (name, email, password_hash)
                VALUES (%s, %s, %s)
                ON CONFLICT (email) DO NOTHING
                RETURNING id
                """,
                (name, email, password_hash),
            )
            row = cur.fetchone()
            if row is None:
                return None
            return row[0]


def get_user_by_email(email):
    # Incluye el hash de la contraseña: solo se usa para iniciar sesión
    with pool.connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                "SELECT id, name, email, password_hash FROM users WHERE email = %s",
                (email,),
            )
            return cur.fetchone()


def get_user(user_id):
    # Datos públicos del usuario de la sesión (sin el hash)
    with pool.connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                "SELECT id, name, email FROM users WHERE id = %s",
                (user_id,),
            )
            return cur.fetchone()


def list_events():
    # Eventos de la cartelera con el total de sillas y cuántas quedan libres
    with pool.connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                """
                SELECT events.id, events.name, events.category, events.venue, events.starts_at,
                       events.is_flash_sale,
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
                SELECT events.id, events.name, events.category, events.venue, events.starts_at,
                       events.is_flash_sale,
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


def list_sections(event_id):
    # Zonas del evento con sus sillas libres y totales, en el orden del seed (por el primer id)
    with pool.connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                """
                SELECT section,
                       count(*) FILTER (WHERE status = 'available') AS available_seats,
                       count(*) AS total_seats
                FROM seats
                WHERE event_id = %s
                GROUP BY section
                ORDER BY min(id)
                """,
                (event_id,),
            )
            return cur.fetchall()


def list_seats(event_id):
    # Todas las sillas del evento con su estado (no dice quién reservó: esta lista es pública)
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


def list_section_seats(event_id, section):
    # Solo las sillas de una zona del evento
    with pool.connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                """
                SELECT id, section, seat_row, seat_number, status
                FROM seats
                WHERE event_id = %s AND section = %s
                ORDER BY id
                """,
                (event_id, section),
            )
            return cur.fetchall()


def get_seat(event_id, seat_id):
    # Una silla con los datos de su evento (para la página Confirmar), o None si no existe en ese evento
    with pool.connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                """
                SELECT seats.id, seats.section, seats.seat_row, seats.seat_number, seats.status,
                       events.id AS event_id, events.name AS event_name, events.category,
                       events.venue, events.starts_at
                FROM seats
                JOIN events ON events.id = seats.event_id
                WHERE seats.id = %s AND seats.event_id = %s
                """,
                (seat_id, event_id),
            )
            return cur.fetchone()


def seat_exists(event_id, seat_id):
    # Sirve para distinguir entre "la silla no existe en este evento" (404) y "ya fue reservada" (409)
    with pool.connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT 1 FROM seats WHERE id = %s AND event_id = %s",
                (seat_id, event_id),
            )
            return cur.fetchone() is not None


def reserve_seat(event_id, seat_id, user_id):
    # Aparta la silla y crea la reserva en UNA sola transacción (la de pool.connection(),
    # que hace commit al final): o se hacen las dos cosas, o ninguna.
    # El UPDATE solo cambia la silla si sigue libre. Si dos personas llegan al tiempo,
    # PostgreSQL hace esperar a la segunda; cuando la primera termina, la silla ya no está
    # 'available' y la segunda no actualiza nada.
    # Devuelve la reserva, o None si no se pudo (la silla no existe o ya estaba reservada).
    with pool.connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                """
                UPDATE seats
                SET status = 'reserved'
                WHERE id = %s AND event_id = %s AND status = 'available'
                RETURNING id, section, seat_row, seat_number
                """,
                (seat_id, event_id),
            )
            seat = cur.fetchone()
            if seat is None:
                return None

            cur.execute(
                """
                INSERT INTO reservations (seat_id, user_id)
                VALUES (%s, %s)
                RETURNING id, created_at
                """,
                (seat_id, user_id),
            )
            reservation = cur.fetchone()

    return {
        "id": reservation["id"],
        "created_at": reservation["created_at"],
        "event_id": event_id,
        "seat_id": seat["id"],
        "section": seat["section"],
        "seat_row": seat["seat_row"],
        "seat_number": seat["seat_number"],
    }


def list_user_reservations(user_id):
    # Reservas de un usuario con los datos del evento y la silla
    with pool.connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                """
                SELECT reservations.id, reservations.created_at,
                       events.id AS event_id, events.name AS event_name, events.category,
                       events.venue, events.starts_at,
                       seats.id AS seat_id, seats.section, seats.seat_row, seats.seat_number
                FROM reservations
                JOIN seats ON seats.id = reservations.seat_id
                JOIN events ON events.id = seats.event_id
                WHERE reservations.user_id = %s
                ORDER BY events.starts_at, reservations.id
                """,
                (user_id,),
            )
            return cur.fetchall()


def get_reservation(reservation_id, user_id):
    # Una reserva SOLO si es del usuario indicado. La de otro usuario se trata como inexistente (404).
    with pool.connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                """
                SELECT reservations.id, reservations.created_at,
                       events.id AS event_id, events.name AS event_name, events.category,
                       events.venue, events.starts_at,
                       seats.id AS seat_id, seats.section, seats.seat_row, seats.seat_number,
                       users.name AS user_name, users.email AS user_email
                FROM reservations
                JOIN seats ON seats.id = reservations.seat_id
                JOIN events ON events.id = seats.event_id
                JOIN users ON users.id = reservations.user_id
                WHERE reservations.id = %s AND reservations.user_id = %s
                """,
                (reservation_id, user_id),
            )
            return cur.fetchone()
