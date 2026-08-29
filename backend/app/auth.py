from functools import lru_cache
from typing import Annotated, Protocol
from uuid import UUID

from fastapi import Depends, HTTPException, Security, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel
from supabase import Client, create_client
from supabase_auth.errors import AuthError

from .config import get_settings

DEVELOPMENT_USER_ID = UUID("00000000-0000-0000-0000-000000000001")


class Principal(BaseModel):
    id: UUID
    email: str | None = None
    display_name: str
    is_anonymous: bool = False


class Authenticator(Protocol):
    def authenticate(self, token: str) -> Principal | None: ...


class DevelopmentAuthenticator:
    def __init__(self, expected_token: str) -> None:
        self.expected_token = expected_token

    def authenticate(self, token: str) -> Principal | None:
        if token != self.expected_token:
            return None
        return Principal(
            id=DEVELOPMENT_USER_ID,
            email="facilitator@local.tickettalks",
            display_name="Tomasz Pilat",
        )


class SupabaseAuthenticator:
    def __init__(self, url: str, service_role_key: str) -> None:
        self.client: Client = create_client(url, service_role_key)

    def authenticate(self, token: str) -> Principal | None:
        try:
            response = self.client.auth.get_user(token)
        except AuthError:
            return None
        user = response.user
        if not user:
            return None
        metadata = user.user_metadata or {}
        display_name = (
            metadata.get("display_name")
            or metadata.get("full_name")
            or metadata.get("name")
            or (user.email or "Facilitator").split("@", maxsplit=1)[0]
        )
        return Principal(
            id=UUID(str(user.id)),
            email=user.email,
            display_name=display_name,
            is_anonymous=bool(getattr(user, "is_anonymous", False)),
        )


@lru_cache
def get_authenticator() -> Authenticator:
    settings = get_settings()
    if settings.supabase_configured:
        return SupabaseAuthenticator(
            settings.supabase_url or "", settings.supabase_service_role_key or ""
        )
    return DevelopmentAuthenticator(settings.demo_auth_token)


bearer = HTTPBearer(auto_error=False)
AuthenticatorDep = Annotated[Authenticator, Depends(get_authenticator)]


def get_current_principal(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Security(bearer)],
    authenticator: AuthenticatorDep,
) -> Principal:
    if not credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Sign in to continue",
            headers={"WWW-Authenticate": "Bearer"},
        )
    principal = authenticator.authenticate(credentials.credentials)
    if not principal:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Session is invalid or expired",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return principal


PrincipalDep = Annotated[Principal, Depends(get_current_principal)]
