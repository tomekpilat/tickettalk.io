from types import SimpleNamespace
from uuid import UUID

import pytest
from fastapi import HTTPException
from fastapi.security import HTTPAuthorizationCredentials
from supabase_auth.errors import AuthError

from app.auth import (
    DEVELOPMENT_USER_ID,
    DevelopmentAuthenticator,
    SupabaseAuthenticator,
    get_current_principal,
)


class StubAuthenticator:
    def __init__(self, principal=None) -> None:
        self.principal = principal
        self.tokens: list[str] = []

    def authenticate(self, token: str):
        self.tokens.append(token)
        return self.principal


def test_development_authenticator_uses_one_explicit_identity() -> None:
    authenticator = DevelopmentAuthenticator("local-token")

    assert authenticator.authenticate("wrong") is None
    principal = authenticator.authenticate("local-token")
    assert principal is not None
    assert principal.id == DEVELOPMENT_USER_ID
    assert principal.display_name == "Tomasz Pilat"


def test_current_principal_requires_a_valid_bearer_session() -> None:
    authenticator = StubAuthenticator()
    with pytest.raises(HTTPException) as missing:
        get_current_principal(None, authenticator)
    assert missing.value.status_code == 401
    assert missing.value.headers == {"WWW-Authenticate": "Bearer"}

    credentials = HTTPAuthorizationCredentials(scheme="Bearer", credentials="expired")
    with pytest.raises(HTTPException, match="Session is invalid"):
        get_current_principal(credentials, authenticator)
    assert authenticator.tokens == ["expired"]

    expected = SimpleNamespace(id=DEVELOPMENT_USER_ID)
    authenticator.principal = expected
    assert get_current_principal(credentials, authenticator) is expected


def test_supabase_authenticator_maps_metadata_and_anonymous_state() -> None:
    user = SimpleNamespace(
        id=UUID("00000000-0000-0000-0000-000000000099"),
        email="maya@example.com",
        user_metadata={"full_name": "Maya Chen"},
        is_anonymous=True,
    )
    authenticator = SupabaseAuthenticator.__new__(SupabaseAuthenticator)
    authenticator.client = SimpleNamespace(
        auth=SimpleNamespace(get_user=lambda _token: SimpleNamespace(user=user))
    )

    principal = authenticator.authenticate("valid")

    assert principal is not None
    assert principal.display_name == "Maya Chen"
    assert principal.email == "maya@example.com"
    assert principal.is_anonymous is True


def test_supabase_authenticator_rejects_provider_errors_and_missing_users() -> None:
    def reject(_token):
        raise AuthError("invalid token", None)

    authenticator = SupabaseAuthenticator.__new__(SupabaseAuthenticator)
    authenticator.client = SimpleNamespace(auth=SimpleNamespace(get_user=reject))
    assert authenticator.authenticate("invalid") is None

    authenticator.client = SimpleNamespace(
        auth=SimpleNamespace(get_user=lambda _token: SimpleNamespace(user=None))
    )
    assert authenticator.authenticate("missing") is None


@pytest.mark.parametrize(
    ("metadata", "email", "expected"),
    [
        ({"display_name": "Display"}, "fallback@example.com", "Display"),
        ({"name": "Named"}, "fallback@example.com", "Named"),
        ({}, "fallback@example.com", "fallback"),
        ({}, None, "Facilitator"),
    ],
)
def test_supabase_authenticator_display_name_fallbacks(metadata, email, expected) -> None:
    user = SimpleNamespace(
        id=UUID("00000000-0000-0000-0000-000000000099"),
        email=email,
        user_metadata=metadata,
        is_anonymous=False,
    )
    authenticator = SupabaseAuthenticator.__new__(SupabaseAuthenticator)
    authenticator.client = SimpleNamespace(
        auth=SimpleNamespace(get_user=lambda _token: SimpleNamespace(user=user))
    )

    assert authenticator.authenticate("valid").display_name == expected
