from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Environment configuration. Secrets come from SSM Parameter Store through External Secrets."""

    model_config = SettingsConfigDict(env_prefix="", case_sensitive=False)

    database_url: str = Field(description="postgresql://user:pass@host:5432/statline")
    api_sports_key: SecretStr = Field(description="API-Sports key (x-apisports-key header)")
    api_sports_timeout_s: float = 15.0
    api_sports_max_retries: int = 3
    # Free plan: ~100 requests per day per sport (proposal §3.3). Stop before the provider does.
    api_sports_daily_quota: int = 95
    # Fallback providers (SL-20, D-26). balldontlie is a secret (SSM `/statline/comun/balldontlie-api-key`);
    # without a key the NBA fallback is disabled. TheSportsDB "3" is its public free test key.
    # Off by default: the fallback field mappings are unverified against the live APIs (D-26).
    fallback_habilitado: bool = False
    balldontlie_api_key: SecretStr = Field(
        default=SecretStr(""), description="balldontlie.io key; empty disables the NBA fallback"
    )
    thesportsdb_api_key: str = "3"
    temporada_basquetbol: str = "2025-2026"
    temporada_americano: str = "2026"
    temporada_futbol: str = "2026"
    schemas_dir: str = Field(
        default="/app/schemas", description="Directory with <deporte>.schema.json files"
    )
    health_port: int = 8080
