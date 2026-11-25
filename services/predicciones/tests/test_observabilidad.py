from unittest.mock import patch

from predicciones.observabilidad import iniciar_sentry, tasa_de_trazas


def test_sin_dsn_no_inicia() -> None:
    with patch("predicciones.observabilidad.sentry_sdk.init") as init:
        assert iniciar_sentry({}) is False
    init.assert_not_called()


def test_con_dsn_inicia_con_ambiente_y_release() -> None:
    env = {
        "SENTRY_DSN": "https://key@o1.ingest.sentry.io/1",
        "SENTRY_ENVIRONMENT": "prod",
        "SENTRY_RELEASE": "abc1234",
        "SENTRY_TRACES_SAMPLE_RATE": "0.1",
    }
    with patch("predicciones.observabilidad.sentry_sdk.init") as init:
        assert iniciar_sentry(env) is True
    kwargs = init.call_args.kwargs
    assert kwargs["environment"] == "prod"
    assert kwargs["release"] == "abc1234"
    assert kwargs["traces_sample_rate"] == 0.1
    assert kwargs["send_default_pii"] is False


def test_tasa_invalida_es_cero() -> None:
    assert tasa_de_trazas(None) == 0.0
    assert tasa_de_trazas("x") == 0.0
    assert tasa_de_trazas("3") == 0.0
    assert tasa_de_trazas("0.5") == 0.5
