-- Esquema de la boletería.
-- La imagen oficial de PostgreSQL ejecuta este archivo una sola vez, cuando el volumen pg-data está vacío.

-- Eventos a la venta. starts_at es la hora local de Cali (sin zona horaria).
CREATE TABLE events (
    id        integer GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    name      varchar(150) NOT NULL,
    venue     varchar(150) NOT NULL,
    starts_at timestamp    NOT NULL
);

-- Sillas de cada evento. Una silla libre tiene status 'available' y los datos del comprador vacíos.
CREATE TABLE seats (
    id          integer GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    event_id    integer      NOT NULL REFERENCES events (id),
    section     varchar(50)  NOT NULL,
    seat_row    varchar(5)   NOT NULL,
    seat_number integer      NOT NULL,
    status      varchar(10)  NOT NULL DEFAULT 'available',
    buyer_name  varchar(100),
    buyer_email varchar(254),
    sold_at     timestamptz,

    CONSTRAINT seats_status_check CHECK (status IN ('available', 'sold')),
    -- Una misma silla no puede existir dos veces en el mismo evento.
    -- Este UNIQUE también crea el índice que se usa para buscar las sillas por event_id.
    CONSTRAINT seats_event_position_unique UNIQUE (event_id, section, seat_row, seat_number)
);
