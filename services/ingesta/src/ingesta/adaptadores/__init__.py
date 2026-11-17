"""Registry: one adapter per sport. The CronJob passes the sport name on the command line."""

from ingesta.adaptadores.americano import AdaptadorAmericano
from ingesta.adaptadores.api_sports import ClienteApiSports
from ingesta.adaptadores.base import AdaptadorDeporte
from ingesta.adaptadores.basquetbol import AdaptadorBasquetbol
from ingesta.adaptadores.futbol import AdaptadorFutbol
from ingesta.config import Settings
from ingesta.modelos import Deporte


def crear_adaptador(deporte: Deporte, settings: Settings) -> AdaptadorDeporte:
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
    if deporte is Deporte.FUTBOL:
        return AdaptadorFutbol(cliente("football"), settings.temporada_futbol)
    # TODO(SL-20): fallbacks balldontlie.io (NBA) and TheSportsDB (NFL, Liga MX).
    raise NotImplementedError(f"adaptador para {deporte} pendiente")


__all__ = ["AdaptadorDeporte", "crear_adaptador"]
