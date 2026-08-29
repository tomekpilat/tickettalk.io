from collections.abc import Callable
from functools import lru_cache
from typing import Annotated

from fastapi import Depends, HTTPException

from .config import get_settings
from .jira_client import JiraClient, TokenCipher
from .repositories import InMemoryRepository, Repository, SupabaseRepository


@lru_cache
def get_repository() -> Repository:
    settings = get_settings()
    if settings.supabase_configured:
        return SupabaseRepository(
            settings.supabase_url or "", settings.supabase_service_role_key or ""
        )
    return InMemoryRepository()


def get_token_cipher() -> TokenCipher:
    key = get_settings().jira_encryption_key
    if not key:
        raise HTTPException(
            status_code=503,
            detail="Jira integration requires JIRA_ENCRYPTION_KEY",
        )
    try:
        return TokenCipher(key)
    except ValueError as error:
        raise HTTPException(status_code=503, detail=str(error)) from error


def get_jira_client_factory() -> Callable[[str, str, str], JiraClient]:
    return JiraClient


RepositoryDep = Annotated[Repository, Depends(get_repository)]
TokenCipherDep = Annotated[TokenCipher, Depends(get_token_cipher)]
JiraClientFactoryDep = Annotated[
    Callable[[str, str, str], JiraClient], Depends(get_jira_client_factory)
]
