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
        # No request bodies, cookies or client IPs; FastAPI is instrumented automatically.
        send_default_pii=False,
        max_request_body_size="never",
    )
    return True
