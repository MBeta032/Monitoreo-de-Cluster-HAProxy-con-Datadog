-- Datos iniciales de la Taquilla Sucursal: usuarios de prueba, un concierto de venta flash
-- con 2.000 sillas y tres eventos pequeños (uno ya agotado).

-- Usuarios SOLO PARA PRUEBAS (demostración y Artillery). Todos tienen la contraseña de prueba
-- "Taquilla2026!" (README, sección 6). El hash se calculó una sola vez con
-- werkzeug.security.generate_password_hash("Taquilla2026!", method="pbkdf2:sha256:600000").
INSERT INTO users (name, email, password_hash) VALUES
    ('Usuario Demo', 'demo@taquilla.test',
     'pbkdf2:sha256:600000$lYDBq9gXmEKaw5Lm$c674e8e547cfa6dacd07a313af94818c56e106f33a2599fe0f886b8fa56ae6bc');

-- 200 usuarios: prueba001@taquilla.test a prueba200@taquilla.test, con el mismo hash
INSERT INTO users (name, email, password_hash)
SELECT 'Prueba ' || lpad(n::text, 3, '0'),
       'prueba' || lpad(n::text, 3, '0') || '@taquilla.test',
       'pbkdf2:sha256:600000$lYDBq9gXmEKaw5Lm$c674e8e547cfa6dacd07a313af94818c56e106f33a2599fe0f886b8fa56ae6bc'
FROM generate_series(1, 200) AS n
ORDER BY n;

-- Cartelera: los eventos son inventados; los lugares son reales de Cali.
INSERT INTO events (name, category, venue, starts_at, is_flash_sale) VALUES
    ('Concierto Caña y Clave', 'Concierto', 'Teatro al Aire Libre Los Cristales', '2026-12-27 20:00', true),
    ('Obra: El Cuentero del Pacífico', 'Teatro', 'Teatro Municipal Enrique Buenaventura', '2026-12-05 19:30', false),
    ('Noche de jazz', 'Música', 'Teatro Jorge Isaacs', '2026-12-12 20:00', false),
    ('Cuentos de medianoche', 'Narración oral', 'Teatrino del Teatro Municipal', '2026-12-19 21:00', false);

-- Concierto (venta flash): 4 zonas x 20 filas (A a T) x 25 sillas = 2.000 sillas (ids 1 a 2000).
-- Orden de los ids: Platea 1-500, Gradería Central 501-1000, Gradería Izquierda 1001-1500,
-- Gradería Derecha 1501-2000. chr(64 + 1) es 'A', chr(64 + 2) es 'B', y así sucesivamente.
INSERT INTO seats (event_id, section, seat_row, seat_number)
SELECT events.id, zones.name, chr(64 + row_index), seat_index
FROM events
CROSS JOIN (VALUES
    (1, 'Platea'),
    (2, 'Gradería Central'),
    (3, 'Gradería Izquierda'),
    (4, 'Gradería Derecha')
) AS zones (position, name)
CROSS JOIN generate_series(1, 20) AS row_index
CROSS JOIN generate_series(1, 25) AS seat_index
WHERE events.name = 'Concierto Caña y Clave'
ORDER BY zones.position, row_index, seat_index;

-- Teatro y jazz: una zona "Platea" de 10 filas (A a J) x 10 sillas = 100 sillas cada uno
-- (ids 2001-2100 y 2101-2200).
INSERT INTO seats (event_id, section, seat_row, seat_number)
SELECT events.id, 'Platea', chr(64 + row_index), seat_index
FROM events
CROSS JOIN generate_series(1, 10) AS row_index
CROSS JOIN generate_series(1, 10) AS seat_index
WHERE events.name IN ('Obra: El Cuentero del Pacífico', 'Noche de jazz')
ORDER BY events.id, row_index, seat_index;

-- Cuentos de medianoche: una zona "Platea" de 5 filas (A a E) x 8 sillas = 40 sillas (ids 2201-2240).
INSERT INTO seats (event_id, section, seat_row, seat_number)
SELECT events.id, 'Platea', chr(64 + row_index), seat_index
FROM events
CROSS JOIN generate_series(1, 5) AS row_index
CROSS JOIN generate_series(1, 8) AS seat_index
WHERE events.name = 'Cuentos de medianoche'
ORDER BY row_index, seat_index;

-- Cuentos de medianoche queda AGOTADO: sus 40 sillas se reparten una por usuario, en orden,
-- entre prueba161 y prueba200 (silla 2201 -> prueba161, ..., silla 2240 -> prueba200).
-- Así ningún usuario queda con 40 reservas, y demo@taquilla.test empieza sin reservas.
INSERT INTO reservations (seat_id, user_id)
SELECT numbered_seats.id, users.id
FROM (
    SELECT seats.id, row_number() OVER (ORDER BY seats.id) AS position
    FROM seats
    JOIN events ON events.id = seats.event_id
    WHERE events.name = 'Cuentos de medianoche'
) AS numbered_seats
JOIN users
  ON users.email = 'prueba' || lpad((160 + numbered_seats.position)::text, 3, '0') || '@taquilla.test'
ORDER BY numbered_seats.id;

UPDATE seats
SET status = 'reserved'
WHERE id IN (SELECT seat_id FROM reservations);
