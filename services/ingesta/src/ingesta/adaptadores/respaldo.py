"""HTTP client and id helpers shared by the fallback providers (balldontlie, TheSportsDB).

Same retry policy as ClienteApiSports: retries on 429, 5xx and network errors with exponential
backoff (a Retry-After header on 429 is honoured, capped); other 4xx fail at once because they are
configuration bugs. Exhausted retries raise ProveedorCaidoError, the signal to switch providers.

Provider ids are namespaced as `<proveedor>:<id>` so an id from a fallback can never collide with an
API-Sports id in the unique keys of `partido`, `equipo` and `jugador` (D-26).
"""

import time
from collections.abc import Mapping
from typing import Any

import httpx

from ingesta.adaptadores.api_sports import ProveedorCaidoError

MAX_ESPERA_S = 60.0
MAX_PAGINAS = 200


class RespuestaRespaldoError(RuntimeError):
    """A fallback answered with a 4xx or an unreadable body. `status` is the HTTP code, if any."""

    def __init__(self, mensaje: str, status: int | None = None) -> None:
        super().__init__(mensaje)
        self.status = status


class ClienteRespaldo:
    def __init__(
        self,
        base_url: str,
        *,
        headers: Mapping[str, str] | None = None,
        timeout_s: float = 15.0,
        max_retries: int = 3,
        backoff_s: float = 1.0,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self._http = httpx.Client(
            base_url=base_url, headers=dict(headers or {}), timeout=timeout_s, transport=transport
        )
        self._max_retries = max_retries
        self._backoff_s = backoff_s
        self.peticiones = 0

    def get(self, path: str, params: Mapping[str, Any] | None = None) -> dict[str, Any]:
        for intento in range(self._max_retries + 1):
            self.peticiones += 1
            espera = self._backoff_s * 2**intento
            try:
                resp = self._http.get(path, params=dict(params or {}))
            except httpx.TransportError as err:
                if intento == self._max_retries:
                    raise ProveedorCaidoError(f"{path}: {err}") from err
            else:
                if resp.status_code == 200:
                    cuerpo = resp.json()
                    if not isinstance(cuerpo, dict):
                        raise RespuestaRespaldoError(f"{path}: el cuerpo no es un objeto JSON")
                    return cuerpo
                if resp.status_code != 429 and resp.status_code < 500:
                    raise RespuestaRespaldoError(
                        f"{path}: HTTP {resp.status_code}", resp.status_code
                    )
                if intento == self._max_retries:
                    raise ProveedorCaidoError(f"{path}: HTTP {resp.status_code} tras reintentos")
                espera = max(espera, _retry_after(resp))
            time.sleep(min(espera, MAX_ESPERA_S))
        raise AssertionError("unreachable")  # pragma: no cover

    def close(self) -> None:
        self._http.close()


def _retry_after(resp: httpx.Response) -> float:
    try:
        return float(resp.headers.get("Retry-After", 0))
    except ValueError:
        return 0.0


def prefijar(proveedor: str, valor: object) -> str:
    return f"{proveedor}:{valor}"


def quitar_prefijo(proveedor: str, valor: str) -> str:
    prefijo = f"{proveedor}:"
    return valor[len(prefijo) :] if valor.startswith(prefijo) else valor


def paginar_cursor(
    cliente: ClienteRespaldo, path: str, params: Mapping[str, Any]
) -> list[dict[str, Any]]:
    """Follows `meta.next_cursor` until it is null (balldontlie v1 pagination)."""
    datos: list[dict[str, Any]] = []
    cursor: str | None = None
    for _ in range(MAX_PAGINAS):
        pagina = {**params, "per_page": 100}
        if cursor is not None:
            pagina["cursor"] = cursor
        cuerpo = cliente.get(path, pagina)
        datos.extend(cuerpo.get("data") or [])
        cursor = (cuerpo.get("meta") or {}).get("next_cursor")
        if cursor is None:
            return datos
    raise RespuestaRespaldoError(f"{path}: más de {MAX_PAGINAS} páginas")
