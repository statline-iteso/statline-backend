"""One ingestion run: games of a date range → box scores of finished games → PostgreSQL.

Every run is recorded in `ejecucion_ingesta` (EN_CURSO → EXITOSA | FALLIDA), including the number
of provider requests it used and the providers that fed it (a fallback shows as "a+b"), so the quota
can be audited from the API (/api/ingestas).
"""

import logging
from dataclasses import dataclass
from datetime import date, timedelta

from ingesta.adaptadores.api_sports import CuotaAgotadaError
from ingesta.adaptadores.base import AdaptadorDeporte
from ingesta.modelos import EstatusPartido
from ingesta.repositorio import Repositorio
from ingesta.validacion import MetricasInvalidasError, validar_metricas

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class ResultadoEjecucion:
    ejecucion_id: str
    exitosa: bool
    partidos: int
    estadisticas: int
    descartadas: int
    error: str | None = None


def ejecutar(
    adaptador: AdaptadorDeporte,
    repo: Repositorio,
    *,
    desde: date,
    hasta: date,
    schemas_dir: str,
) -> ResultadoEjecucion:
    ejecucion_id = repo.iniciar_ejecucion(adaptador.deporte, adaptador.proveedor)
    partidos = estadisticas = descartadas = 0
    error: str | None = None
    try:
        liga_id = repo.liga_id(adaptador.deporte, adaptador.proveedor, adaptador.proveedor_liga_id)
        dia = desde
        while dia <= hasta:
            for partido in adaptador.partidos_del_dia(dia):
                partido_id = repo.guardar_partido(liga_id, partido)
                partidos += 1
                if partido.estatus is not EstatusPartido.FINALIZADO:
                    continue
                for linea in adaptador.lineas_del_partido(partido.proveedor_id):
                    try:
                        validar_metricas(schemas_dir, adaptador.deporte, linea.metricas)
                    except MetricasInvalidasError as err:
                        # One bad line must not lose the whole game: skip it and keep going.
                        descartadas += 1
                        log.warning("línea descartada: %s", err)
                        continue
                    repo.guardar_estadistica(adaptador.deporte, liga_id, partido_id, linea)
                    estadisticas += 1
            dia += timedelta(days=1)
    except CuotaAgotadaError as err:
        # Partial data is kept; the next scheduled run picks up where this one stopped.
        error = str(err)
    except Exception as err:
        error = f"{type(err).__name__}: {err}"
        log.exception("ingesta fallida")

    exitosa = error is None
    repo.finalizar_ejecucion(
        ejecucion_id,
        exitosa=exitosa,
        registros=partidos + estadisticas,
        peticiones=adaptador.peticiones_usadas(),
        proveedor=adaptador.proveedor_efectivo(),
        error=error,
    )
    return ResultadoEjecucion(ejecucion_id, exitosa, partidos, estadisticas, descartadas, error)
