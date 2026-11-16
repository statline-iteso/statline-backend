from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Environment configuration. Secrets come from Key Vault through the CSI driver."""

    model_config = SettingsConfigDict(env_prefix="", case_sensitive=False)

    database_url: str = Field(description="postgresql://user:pass@host:5432/statline")
    api_sports_key: SecretStr = Field(description="API-Sports key (x-apisports-key header)")
    api_sports_timeout_s: float = 15.0
    api_sports_max_retries: int = 3
    # Free plan: ~100 requests per day per sport (proposal §3.3). Stop before the provider does.
    api_sports_daily_quota: int = 95
    temporada_basquetbol: str = "2025-2026"
    temporada_americano: str = "2026"
    temporada_futbol: str = "2026"
    schemas_dir: str = Field(
        default="/app/schemas", description="Directory with <deporte>.schema.json files"
    )
    health_port: int = 8080
