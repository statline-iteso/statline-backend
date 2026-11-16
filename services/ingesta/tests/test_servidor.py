import threading
from collections.abc import Iterator
from http.server import ThreadingHTTPServer

import httpx
import pytest

from ingesta.servidor import crear_handler


@pytest.fixture
def servidor() -> Iterator[tuple[str, list[bool]]]:
    estado = [True]
    srv = ThreadingHTTPServer(("127.0.0.1", 0), crear_handler(lambda: estado[0]))
    hilo = threading.Thread(target=srv.serve_forever, daemon=True)
    hilo.start()
    yield f"http://127.0.0.1:{srv.server_address[1]}", estado
    srv.shutdown()


def test_probes_y_metricas(servidor: tuple[str, list[bool]]) -> None:
    url, estado = servidor
    assert httpx.get(f"{url}/healthz").json() == {"status": "ok"}
    assert httpx.get(f"{url}/readyz").status_code == 200
    estado[0] = False
    assert httpx.get(f"{url}/readyz").status_code == 503
    assert "python_info" in httpx.get(f"{url}/metrics").text
    assert httpx.get(f"{url}/otra").status_code == 404
