import io
import os
import tempfile
from pathlib import Path

import pytest
from psycopg_pool import ConnectionPool

# prometheus-client lee PROMETHEUS_MULTIPROC_DIR al importarse,
# por eso se define aquí, antes de importar la app.
os.environ["PROMETHEUS_MULTIPROC_DIR"] = tempfile.mkdtemp(prefix="prometheus_multiproc_")

import app as backend_app  # noqa: E402
import db  # noqa: E402

# Base de datos de prueba (por ejemplo postgresql://postgres@127.0.0.1:5433/boleteria_test).
# Si no está definida, las pruebas que la necesitan se saltan (ver test_database.py).
TEST_DATABASE_URL = os.getenv("TEST_DATABASE_URL")

# Carpeta con el esquema y los datos iniciales: los mismos archivos que usa el servicio db
DB_INIT_DIR = Path(__file__).resolve().parents[2] / "db" / "init"


@pytest.fixture
def client():
    return backend_app.app.test_client()


@pytest.fixture
def log_stream():
    # Durante la prueba, los logs JSON de la app se escriben en memoria para poder leerlos
    stream = io.StringIO()
    previous_stream = backend_app.handler.setStream(stream)
    yield stream
    backend_app.handler.setStream(previous_stream)


@pytest.fixture
def unreachable_database(monkeypatch):
    # Simula la base de datos caída: un pool que apunta a un puerto donde no hay PostgreSQL.
    # Con timeout=1, la petición espera 1 segundo por una conexión y el pool lanza PoolTimeout.
    unreachable_pool = ConnectionPool(
        conninfo="host=127.0.0.1 port=1 connect_timeout=1",
        min_size=1,
        max_size=1,
        timeout=1,
        open=True,
    )
    monkeypatch.setattr(db, "pool", unreachable_pool)
    yield
    unreachable_pool.close()


@pytest.fixture(scope="session")
def test_pool():
    # Un solo pool hacia la base de prueba para toda la sesión de pytest
    pool = ConnectionPool(conninfo=TEST_DATABASE_URL, min_size=1, max_size=2, open=True)
    pool.wait()
    yield pool
    pool.close()


@pytest.fixture
def database(test_pool, monkeypatch):
    # Deja la base de prueba como recién creada antes de cada prueba:
    # borra las tablas y vuelve a cargar 01_schema.sql y 02_seed.sql.
    # Así los id del seed siempre son los mismos (concierto = evento 1, sillas 1 a 2000).
    schema_sql = (DB_INIT_DIR / "01_schema.sql").read_text(encoding="utf-8")
    seed_sql = (DB_INIT_DIR / "02_seed.sql").read_text(encoding="utf-8")
    with test_pool.connection() as conn:
        conn.execute("DROP TABLE IF EXISTS seats, events")
        # Sin parámetros, psycopg permite varias sentencias en un mismo execute
        conn.execute(schema_sql)
        conn.execute(seed_sql)

    # La app usa este pool en lugar del suyo durante la prueba
    monkeypatch.setattr(db, "pool", test_pool)
