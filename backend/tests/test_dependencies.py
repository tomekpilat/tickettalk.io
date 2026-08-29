import pytest
from fastapi import HTTPException

from app import dependencies
from app.config import Settings
from app.jira_client import JiraClient, generate_encryption_key
from app.repositories import InMemoryRepository


def test_repository_dependency_selects_memory_or_supabase(monkeypatch) -> None:
    monkeypatch.setattr(dependencies, "get_settings", lambda: Settings(app_env="test"))
    dependencies.get_repository.cache_clear()
    assert isinstance(dependencies.get_repository(), InMemoryRepository)

    sentinel = object()
    monkeypatch.setattr(
        dependencies,
        "get_settings",
        lambda: Settings(
            app_env="test",
            supabase_url="https://example.supabase.co",
            supabase_service_role_key="service-role-key",
        ),
    )
    monkeypatch.setattr(dependencies, "SupabaseRepository", lambda *_: sentinel)
    dependencies.get_repository.cache_clear()
    assert dependencies.get_repository() is sentinel
    dependencies.get_repository.cache_clear()


def test_token_cipher_dependency_requires_a_valid_configured_key(monkeypatch) -> None:
    monkeypatch.setattr(dependencies, "get_settings", lambda: Settings(app_env="test"))
    with pytest.raises(HTTPException, match="JIRA_ENCRYPTION_KEY") as missing:
        dependencies.get_token_cipher()
    assert missing.value.status_code == 503

    monkeypatch.setattr(
        dependencies,
        "get_settings",
        lambda: Settings(app_env="test", jira_encryption_key="not-a-fernet-key"),
    )
    with pytest.raises(HTTPException, match="valid Fernet key") as invalid:
        dependencies.get_token_cipher()
    assert invalid.value.status_code == 503

    key = generate_encryption_key()
    monkeypatch.setattr(
        dependencies,
        "get_settings",
        lambda: Settings(app_env="test", jira_encryption_key=key),
    )
    cipher = dependencies.get_token_cipher()
    assert cipher.decrypt(cipher.encrypt("jira-token")) == "jira-token"


def test_jira_client_factory_uses_the_production_client() -> None:
    assert dependencies.get_jira_client_factory() is JiraClient
