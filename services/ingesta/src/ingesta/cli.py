"""Entry point.

    ingesta run basquetbol [--desde YYYY-MM-DD] [--hasta YYYY-MM-DD]   # what each CronJob runs
    ingesta serve                                                       # /healthz /readyz /metrics

`run` defaults to yesterday and today (UTC), so a daily schedule catches late finals.
"""

import argparse
import logging
import sys
from datetime import UTC, date, datetime, timedelta

from prometheus_client import Counter, Gauge

from ingesta.adaptadores import crear_adaptador
from ingesta.config import Settings
from ingesta.ejecutor import ejecutar
from ingesta.modelos import Deporte
from ingesta.repositorio import RepositorioPostgres
from ingesta.servidor import servir

EJECUCIONES = Counter("statline_ingesta_runs_total", "Ingestion runs", ["deporte", "resultado"])
REGISTROS = Gauge("statline_ingesta_last_records", "Records stored by the last run", ["deporte"])


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="ingesta")
    sub = parser.add_subparsers(dest="comando", required=True)
    run = sub.add_parser("run", help="ingest one sport")
    run.add_argument("deporte", choices=[d.value.lower() for d in Deporte])
    run.add_argument("--desde", type=date.fromisoformat)
    run.add_argument("--hasta", type=date.fromisoformat)
    sub.add_parser("serve", help="health and metrics server")
    return parser


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    args = _parser().parse_args(argv)
    settings = Settings()  # type: ignore[call-arg]  # filled from the environment

    if args.comando == "serve":
        servir(settings)
        return 0

    deporte = Deporte(args.deporte.upper())
    hoy = datetime.now(UTC).date()
    desde = args.desde or hoy - timedelta(days=1)
    hasta = args.hasta or hoy

    adaptador = crear_adaptador(deporte, settings)
    repo = RepositorioPostgres.conectar(settings.database_url)
    resultado = ejecutar(
        adaptador, repo, desde=desde, hasta=hasta, schemas_dir=settings.schemas_dir
    )
    EJECUCIONES.labels(deporte.value, "ok" if resultado.exitosa else "error").inc()
    REGISTROS.labels(deporte.value).set(resultado.partidos + resultado.estadisticas)
    logging.getLogger("ingesta").info("resultado %s", resultado)
    # Non-zero exit marks the Job as failed so Kubernetes (and the alerts) see it.
    return 0 if resultado.exitosa else 1


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
