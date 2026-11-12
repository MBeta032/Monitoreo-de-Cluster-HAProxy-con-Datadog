-- Esquema de la Taquilla Sucursal.
-- La imagen oficial de PostgreSQL ejecuta este archivo una sola vez, cuando el volumen pg-data está vacío.

-- Usuarios de la taquilla. El correo se guarda en minúsculas para que sea único sin importar mayúsculas.
-- password_hash guarda el hash de werkzeug.security, nunca la contraseña.
CREATE TABLE users (
    id            integer GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    name          varchar(100) NOT NULL,
    email         varchar(254) NOT NULL,
    password_hash varchar(255) NOT NULL,
    created_at    timestamptz  NOT NULL DEFAULT now(),

    CONSTRAINT users_email_unique UNIQUE (email),
    CONSTRAINT users_email_lowercase CHECK (email = lower(email))
);

-- Eventos de la cartelera. starts_at es la hora local de Cali (sin zona horaria).
-- is_flash_sale marca el evento que la cartelera destaca como venta flash.
CREATE TABLE events (
    id            integer GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    name          varchar(150) NOT NULL,
    category      varchar(30)  NOT NULL,
    venue         varchar(150) NOT NULL,
    starts_at     timestamp    NOT NULL,
    is_flash_sale boolean      NOT NULL DEFAULT false,

    CONSTRAINT events_category_check CHECK (category IN ('Concierto', 'Teatro', 'Música', 'Narración oral'))
);

-- Sillas de cada evento, agrupadas por zona (section). Una silla libre tiene status 'available';
-- al confirmar una reserva pasa a 'reserved'.
CREATE TABLE seats (
    id          integer GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    event_id    integer     NOT NULL REFERENCES events (id),
    section     varchar(50) NOT NULL,
    seat_row    varchar(5)  NOT NULL,
    seat_number integer     NOT NULL,
    status      varchar(10) NOT NULL DEFAULT 'available',

    CONSTRAINT seats_status_check CHECK (status IN ('available', 'reserved')),
    -- Una misma silla no puede existir dos veces en el mismo evento.
    -- Este UNIQUE también crea el índice que se usa para buscar las sillas por event_id.
    CONSTRAINT seats_event_position_unique UNIQUE (event_id, section, seat_row, seat_number)
);

-- Reservas. Cada silla tiene como máximo una reserva (UNIQUE en seat_id).
-- El código que ve el usuario es "TS-" más el id con 6 dígitos (TS-000482).
CREATE TABLE reservations (
    id         integer     GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    seat_id    integer     NOT NULL REFERENCES seats (id),
    user_id    integer     NOT NULL REFERENCES users (id),
    created_at timestamptz NOT NULL DEFAULT now(),

    CONSTRAINT reservations_seat_unique UNIQUE (seat_id)
);

-- "Mis reservas" busca por usuario
CREATE INDEX reservations_user_id_index ON reservations (user_id);
