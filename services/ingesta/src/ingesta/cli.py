"""Entry point.

    ingesta run basquetbol [--desde YYYY-MM-DD] [--hasta YYYY-MM-DD]   # what each CronJob runs
    ingesta serve                                                       # /healthz /readyz /metrics
    ingesta seed-demo --confirmar [--deportes ...] [--semilla 42] [--dias 60]   # dev only

`run` defaults to yesterday and today (UTC), so a daily schedule catches late finals.
`seed-demo` writes synthetic data (provider `demo`); no CronJob runs it.
"""

import argparse
import logging
import os
import sys
from datetime import UTC, date, datetime, timedelta

from prometheus_client import Counter, Gauge

from ingesta.adaptadores import crear_adaptador
from ingesta.config import Settings
from ingesta.demo import DIAS_DEFAULT, SEMILLA_DEFAULT, ResultadoDemo, sembrar
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
    demo = sub.add_parser("seed-demo", help="synthetic demo data (dev only)")
    demo.add_argument("--deportes", type=_deportes, default=list(Deporte))
    demo.add_argument("--semilla", type=int, default=SEMILLA_DEFAULT)
    demo.add_argument("--dias", type=_dias, default=DIAS_DEFAULT)
    demo.add_argument("--confirmar", action="store_true", help="required: writes to the database")
    return parser


def _deportes(valor: str) -> list[Deporte]:
    validos = {d.value.lower(): d for d in Deporte}
    elegidos: list[Deporte] = []
    for nombre in valor.split(","):
        clave = nombre.strip().lower()
        if clave not in validos:
            raise argparse.ArgumentTypeError(f"deporte desconocido: {nombre!r}")
        elegidos.append(validos[clave])
    return elegidos


def _dias(valor: str) -> int:
    dias = int(valor)
    if dias < 1:
        raise argparse.ArgumentTypeError("--dias debe ser al menos 1")
    return dias


def _seed_demo(args: argparse.Namespace, settings: Settings) -> int:
    hoy = datetime.now(UTC).date()
    temporadas = {
        Deporte.BASQUETBOL: settings.temporada_basquetbol,
        Deporte.AMERICANO: settings.temporada_americano,
        Deporte.FUTBOL: settings.temporada_futbol,
    }
    repo = RepositorioPostgres.conectar(settings.database_url)
    resultados: list[ResultadoDemo] = []
    for deporte in args.deportes:
        resultado = sembrar(
            repo,
            deporte,
            temporada=temporadas[deporte],
            semilla=args.semilla,
            dias=args.dias,
            hoy=hoy,
            schemas_dir=settings.schemas_dir,
        )
        logging.getLogger("ingesta").info("seed-demo %s", resultado)
        resultados.append(resultado)
    return 0 if all(r.exitosa for r in resultados) else 1


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    args = _parser().parse_args(argv)
    if args.comando == "seed-demo" and not args.confirmar:
        # Checked before reading the environment: a forgotten flag must never write data.
        logging.getLogger("ingesta").error(
            "seed-demo escribe datos sintéticos en la base; agrega --confirmar para ejecutarlo"
        )
        return 2
    if args.comando == "seed-demo":
        os.environ.setdefault("API_SPORTS_KEY", "demo")  # synthetic data never calls the provider
    settings = Settings()  # type: ignore[call-arg]  # filled from the environment

    if args.comando == "serve":
        servir(settings)
        return 0
    if args.comando == "seed-demo":
        return _seed_demo(args, settings)

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
