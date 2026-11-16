from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="", case_sensitive=False)

    database_url: str = ""
    # Trained artifacts (joblib). ModeloPrediccion.artefacto_uri points inside this directory.
    artefactos_dir: str = "/models"
    log_level: str = "info"
