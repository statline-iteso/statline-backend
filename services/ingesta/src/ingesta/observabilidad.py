"""Sentry error monitoring (statline-infra D-43). Off without SENTRY_DSN: local runs and tests
send nothing.

- SENTRY_ENVIRONMENT: staging or prod (chart ConfigMap).
- SENTRY_RELEASE: the commit the image was built from (Dockerfile build arg), so an error points
  to the code that ran even after the image is promoted to prod under another tag.
- SENTRY_TRACES_SAMPLE_RATE: share of requests traced, 0 to 1 (default 0: errors only).
"""

import os
from collections.abc import Mapping

import sentry_sdk
from sentry_sdk.crons import capture_checkin
from sentry_sdk.crons.consts import MonitorStatus
from sentry_sdk.types import MonitorConfig


def tasa_de_trazas(valor: str | None) -> float:
    try:
        tasa = float(valor or "0")
    except ValueError:
        return 0.0
    return tasa if 0.0 <= tasa <= 1.0 else 0.0


def iniciar_sentry(env: Mapping[str, str] = os.environ) -> bool:
    dsn = env.get("SENTRY_DSN", "")
    # Not an https URL (unset, or Terraform's "set-me" placeholder in SSM): Sentry stays off.
    # sentry_sdk.init would raise on an invalid DSN and crash the service.
    if not dsn.startswith("https://"):
        return False
    sentry_sdk.init(
        dsn=dsn,
        environment=env.get("SENTRY_ENVIRONMENT") or "development",
        release=env.get("SENTRY_RELEASE") or None,
        traces_sample_rate=tasa_de_trazas(env.get("SENTRY_TRACES_SAMPLE_RATE")),
        # No request bodies, cookies or client IPs; logs at ERROR become events.
        send_default_pii=False,
        max_request_body_size="never",
    )
    return True


# Sentry Crons: each `ingesta run <deporte>` reports a check-in, so Sentry alerts when a run fails
# or never starts. The chart sets SENTRY_MONITOR_SCHEDULE to the CronJob's schedule; the monitor
# is created on the first check-in (upsert) with that schedule.
def monitor_config(env: Mapping[str, str] = os.environ) -> MonitorConfig | None:
    horario = env.get("SENTRY_MONITOR_SCHEDULE", "")
    if not horario:
        return None
    return {
        "schedule": {"type": "crontab", "value": horario},
        "timezone": "Etc/UTC",  # CronJobs without timeZone run in the controller's UTC
        "checkin_margin": 15,  # minutes late before "missed"
        "max_runtime": 30,  # minutes before "timed out"
    }


def iniciar_checkin(slug: str) -> str | None:
    if not sentry_sdk.get_client().is_active():
        return None
    return capture_checkin(
        monitor_slug=slug, status=MonitorStatus.IN_PROGRESS, monitor_config=monitor_config()
    )


def terminar_checkin(
    slug: str, checkin_id: str | None, *, exitosa: bool, duracion_s: float
) -> None:
    if checkin_id is None:
        return
    capture_checkin(
        monitor_slug=slug,
        check_in_id=checkin_id,
        status=MonitorStatus.OK if exitosa else MonitorStatus.ERROR,
        duration=duracion_s,
    )
    sentry_sdk.flush(timeout=5)  # the Job exits right after
