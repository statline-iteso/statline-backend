from unittest.mock import patch

from ingesta.observabilidad import (
    iniciar_checkin,
    iniciar_sentry,
    monitor_config,
    tasa_de_trazas,
    terminar_checkin,
)


def test_sin_dsn_no_inicia() -> None:
    with patch("ingesta.observabilidad.sentry_sdk.init") as init:
        assert iniciar_sentry({}) is False
    init.assert_not_called()


def test_con_dsn_inicia_con_ambiente_y_release() -> None:
    env = {
        "SENTRY_DSN": "https://key@o1.ingest.sentry.io/1",
        "SENTRY_ENVIRONMENT": "prod",
        "SENTRY_RELEASE": "abc1234",
        "SENTRY_TRACES_SAMPLE_RATE": "0.1",
    }
    with patch("ingesta.observabilidad.sentry_sdk.init") as init:
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


def test_monitor_config_toma_el_horario_del_cronjob() -> None:
    assert monitor_config({}) is None
    config = monitor_config({"SENTRY_MONITOR_SCHEDULE": "0 8 * * 1,5"})
    assert config is not None
    assert config["schedule"] == {"type": "crontab", "value": "0 8 * * 1,5"}


def test_checkin_apagado_sin_sentry() -> None:
    with patch("ingesta.observabilidad.capture_checkin") as checkin:
        checkin_id = iniciar_checkin("ingesta-futbol")
        terminar_checkin("ingesta-futbol", checkin_id, exitosa=True, duracion_s=1.0)
    assert checkin_id is None
    checkin.assert_not_called()


def test_checkin_reporta_error_si_la_corrida_falla() -> None:
    with (
        patch("ingesta.observabilidad.sentry_sdk.get_client") as cliente,
        patch("ingesta.observabilidad.sentry_sdk.flush"),
        patch("ingesta.observabilidad.capture_checkin", return_value="c1") as checkin,
    ):
        cliente.return_value.is_active.return_value = True
        checkin_id = iniciar_checkin("ingesta-futbol")
        terminar_checkin("ingesta-futbol", checkin_id, exitosa=False, duracion_s=2.0)
    assert checkin_id == "c1"
    assert checkin.call_args_list[0].kwargs["status"] == "in_progress"
    final = checkin.call_args_list[1].kwargs
    assert final["status"] == "error"
    assert final["check_in_id"] == "c1"
