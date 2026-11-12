import io
import os
import tempfile

import pytest

# prometheus-client lee PROMETHEUS_MULTIPROC_DIR al importarse,
# por eso se define aquí, antes de importar la app.
os.environ["PROMETHEUS_MULTIPROC_DIR"] = tempfile.mkdtemp(prefix="prometheus_multiproc_")

import app as backend_app  # noqa: E402


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
