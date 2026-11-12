-- Datos iniciales: un concierto de venta flash y dos eventos pequeños para tráfico normal.
-- Los nombres de los eventos son inventados; los lugares son reales de Cali.

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

INSERT INTO events (name, venue, starts_at) VALUES
    ('Concierto Caña y Clave - Venta flash', 'Arena Cañaveralejo', '2026-12-27 20:00'),
    ('Obra de teatro: El Cuentero del Pacífico', 'Teatro Municipal Enrique Buenaventura', '2026-12-05 19:30'),
    ('Noche de jazz en el Jorge Isaacs', 'Teatro Jorge Isaacs', '2026-12-12 20:00');

-- Concierto: 2 secciones x 20 filas (A a T) x 50 sillas = 2.000 sillas.
-- chr(64 + 1) es 'A', chr(64 + 2) es 'B', y así sucesivamente.
-- El ORDER BY hace que los id queden en orden: primero Preferencial, luego General.
INSERT INTO seats (event_id, section, seat_row, seat_number)
SELECT events.id, sections.name, chr(64 + row_index), seat_index
FROM events
CROSS JOIN (VALUES (1, 'Preferencial'), (2, 'General')) AS sections (position, name)
CROSS JOIN generate_series(1, 20) AS row_index
CROSS JOIN generate_series(1, 50) AS seat_index
WHERE events.name = 'Concierto Caña y Clave - Venta flash'
ORDER BY sections.position, row_index, seat_index;

-- Eventos pequeños: 1 sección x 10 filas (A a J) x 10 sillas = 100 sillas cada uno.
INSERT INTO seats (event_id, section, seat_row, seat_number)
SELECT events.id, 'Platea', chr(64 + row_index), seat_index
FROM events
CROSS JOIN generate_series(1, 10) AS row_index
CROSS JOIN generate_series(1, 10) AS seat_index
WHERE events.name IN ('Obra de teatro: El Cuentero del Pacífico', 'Noche de jazz en el Jorge Isaacs')
ORDER BY events.id, row_index, seat_index;
