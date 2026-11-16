"""HTTP client for API-Sports (api-basketball, api-american-football, api-football).

All three APIs share the same contract: `x-apisports-key` header,
`{"errors": ..., "response": [...]}` bodies and a daily request quota.
Retries cover 429 and 5xx with exponential backoff.
"""

import time
from typing import Any

import httpx

BASE_URLS = {
    "basketball": "https://v1.basketball.api-sports.io",
    "american-football": "https://v1.american-football.api-sports.io",
    "football": "https://v3.football.api-sports.io",
}


class CuotaAgotadaError(RuntimeError):
    """The run used its request budget; the next scheduled run continues."""


class ApiSportsError(RuntimeError):
    pass


class ClienteApiSports:
    def __init__(
        self,
        api: str,
        api_key: str,
        *,
        timeout_s: float = 15.0,
        max_retries: int = 3,
        cuota: int = 95,
        backoff_s: float = 1.0,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self._http = httpx.Client(
            base_url=BASE_URLS[api],
            headers={"x-apisports-key": api_key},
            timeout=timeout_s,
            transport=transport,
        )
        self._max_retries = max_retries
        self._cuota = cuota
        self._backoff_s = backoff_s
        self.peticiones = 0

    def get(self, path: str, params: dict[str, Any]) -> list[dict[str, Any]]:
        for intento in range(self._max_retries + 1):
            if self.peticiones >= self._cuota:
                raise CuotaAgotadaError(f"cuota de {self._cuota} peticiones agotada")
            self.peticiones += 1
            try:
                resp = self._http.get(path, params=params)
            except httpx.TransportError as err:
                if intento == self._max_retries:
                    raise ApiSportsError(f"{path}: {err}") from err
            else:
                if resp.status_code == 200:
                    body = resp.json()
                    # API-Sports answers 200 with a non-empty "errors" for bad keys or params.
                    if body.get("errors"):
                        raise ApiSportsError(f"{path}: {body['errors']}")
                    return list(body.get("response", []))
                if resp.status_code != 429 and resp.status_code < 500:
                    raise ApiSportsError(f"{path}: HTTP {resp.status_code}")
                if intento == self._max_retries:
                    raise ApiSportsError(f"{path}: HTTP {resp.status_code} tras reintentos")
            time.sleep(self._backoff_s * 2**intento)
        raise AssertionError("unreachable")  # pragma: no cover

    def close(self) -> None:
        self._http.close()
