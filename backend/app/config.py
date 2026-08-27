from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "tickettalks api"
    frontend_origin: str = "http://localhost:5173"
    supabase_url: str | None = None
    supabase_service_role_key: str | None = None

    model_config = SettingsConfigDict(env_file=("../.env", ".env"), extra="ignore")


@lru_cache
def get_settings() -> Settings:
    return Settings()

