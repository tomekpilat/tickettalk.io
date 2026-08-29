from functools import lru_cache
from typing import Literal

from pydantic import PositiveInt, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "tickettalk api"
    app_env: Literal["development", "test", "production"] = "development"
    frontend_origin: str = "http://localhost:5173"
    supabase_url: str | None = None
    supabase_service_role_key: str | None = None
    jira_encryption_key: str | None = None
    jira_oauth_client_id: str | None = None
    jira_oauth_client_secret: str | None = None
    jira_oauth_redirect_uri: str | None = None
    demo_auth_token: str = "dev-facilitator"
    rate_limit_join_per_minute: PositiveInt = 20
    rate_limit_import_per_minute: PositiveInt = 12
    rate_limit_vote_per_minute: PositiveInt = 120

    model_config = SettingsConfigDict(env_file=("../.env", ".env"), extra="ignore")

    @model_validator(mode="after")
    def require_supabase_in_production(self) -> "Settings":
        if self.app_env == "production" and not (
            self.supabase_url and self.supabase_service_role_key
        ):
            raise ValueError("Production requires SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY")
        return self

    @property
    def supabase_configured(self) -> bool:
        return bool(self.supabase_url and self.supabase_service_role_key)

@lru_cache
def get_settings() -> Settings:
    return Settings()
