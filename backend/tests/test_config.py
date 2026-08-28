import pytest
from pydantic import ValidationError

from app.auth import DevelopmentAuthenticator
from app.config import Settings


def test_production_requires_supabase_credentials() -> None:
    with pytest.raises(ValidationError, match="Production requires SUPABASE_URL"):
        Settings(
            app_env="production",
            supabase_url=None,
            supabase_service_role_key=None,
            _env_file=None,
        )


def test_development_authenticator_accepts_only_its_explicit_token() -> None:
    authenticator = DevelopmentAuthenticator("local-only-token")

    assert authenticator.authenticate("local-only-token") is not None
    assert authenticator.authenticate("anything-else") is None
