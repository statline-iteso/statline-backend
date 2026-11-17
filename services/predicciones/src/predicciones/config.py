from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="", case_sensitive=False)

    database_url: str = ""
    # Local cache of model artifacts (joblib, verified by sha256). Source of truth is Postgres.
    artefactos_dir: str = "/tmp/statline-modelos"
    log_level: str = "info"
