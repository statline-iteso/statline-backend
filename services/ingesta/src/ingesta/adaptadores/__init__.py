"""Registry: one adapter per sport. The CronJob passes the sport name on the command line.

Each sport gets its API-Sports adapter, wrapped with a fallback provider when one is configured
(NBA: balldontlie, needs BALLDONTLIE_API_KEY; NFL and Liga MX: TheSportsDB). D-17.
"""

import logging

from ingesta.adaptadores.americano import AdaptadorAmericano
from ingesta.adaptadores.api_sports import ClienteApiSports
from ingesta.adaptadores.balldontlie import BASE_URL as BALLDONTLIE_URL
from ingesta.adaptadores.balldontlie import AdaptadorBalldontlie
from ingesta.adaptadores.base import AdaptadorDeporte
from ingesta.adaptadores.basquetbol import AdaptadorBasquetbol
from ingesta.adaptadores.con_respaldo import AdaptadorConRespaldo
from ingesta.adaptadores.futbol import AdaptadorFutbol
from ingesta.adaptadores.respaldo import ClienteRespaldo
from ingesta.adaptadores.thesportsdb import BASE_URL as THESPORTSDB_URL
from ingesta.adaptadores.thesportsdb import AdaptadorTheSportsDB
from ingesta.config import Settings
from ingesta.modelos import Deporte

log = logging.getLogger(__name__)


def crear_adaptador(deporte: Deporte, settings: Settings) -> AdaptadorDeporte:
    principal = _principal(deporte, settings)
    if not settings.fallback_habilitado:
        return principal
    respaldo = _respaldo(deporte, settings)
    if respaldo is None:
        log.info("sin respaldo para %s: falta BALLDONTLIE_API_KEY", deporte.value)
        return principal
    return AdaptadorConRespaldo(principal, respaldo)


def _principal(deporte: Deporte, settings: Settings) -> AdaptadorDeporte:
    def cliente(api: str) -> ClienteApiSports:
        return ClienteApiSports(
            api,
            settings.api_sports_key.get_secret_value(),
            timeout_s=settings.api_sports_timeout_s,
            max_retries=settings.api_sports_max_retries,
            cuota=settings.api_sports_daily_quota,
        )

    if deporte is Deporte.BASQUETBOL:
        return AdaptadorBasquetbol(cliente("basketball"), settings.temporada_basquetbol)
    if deporte is Deporte.AMERICANO:
        return AdaptadorAmericano(cliente("american-football"), settings.temporada_americano)
    return AdaptadorFutbol(cliente("football"), settings.temporada_futbol)


def _respaldo(deporte: Deporte, settings: Settings) -> AdaptadorDeporte | None:
    if deporte is Deporte.BASQUETBOL:
        clave = settings.balldontlie_api_key.get_secret_value()
        if not clave:
            return None
        cliente = ClienteRespaldo(BALLDONTLIE_URL, headers={"Authorization": clave})
        return AdaptadorBalldontlie(cliente, settings.temporada_basquetbol)
    cliente = ClienteRespaldo(f"{THESPORTSDB_URL}/{settings.thesportsdb_api_key}")
    temporada = (
        settings.temporada_americano if deporte is Deporte.AMERICANO else settings.temporada_futbol
    )
    return AdaptadorTheSportsDB(cliente, deporte, temporada)


__all__ = ["AdaptadorDeporte", "crear_adaptador"]


__all__ = ["AdaptadorDeporte", "crear_adaptador"]
