from urllib.parse import parse_qs, urlparse

import httpx
import pytest

from app.jira_client import JiraError
from app.jira_oauth import AtlassianOAuthClient


def test_oauth_builds_authorization_url_and_exchanges_rotating_tokens() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if request.url.path == "/oauth/token/accessible-resources":
            return httpx.Response(
                200,
                json=[
                    {
                        "id": "cloud-123",
                        "url": "https://example.atlassian.net",
                        "name": "Example Jira",
                    }
                ],
            )
        return httpx.Response(
            200,
            json={
                "access_token": "access-2",
                "refresh_token": "refresh-2",
                "expires_in": 3600,
            },
        )

    oauth = AtlassianOAuthClient(
        "client-id",
        "client-secret",
        "https://tickettalk.io/jira/oauth/callback",
        transport=httpx.MockTransport(handler),
    )
    query = parse_qs(urlparse(oauth.authorization_url("encrypted-state")).query)
    assert query["audience"] == ["api.atlassian.com"]
    assert query["response_type"] == ["code"]
    assert query["state"] == ["encrypted-state"]
    assert "offline_access" in query["scope"][0]

    exchanged = oauth.exchange_code("authorization-code")
    refreshed = oauth.refresh("refresh-1")
    resources = oauth.accessible_resources(exchanged.access_token)

    assert exchanged.refresh_token == "refresh-2"
    assert refreshed.access_token == "access-2"
    assert resources[0].id == "cloud-123"
    assert requests[0].url.host == "auth.atlassian.com"
    assert requests[-1].url.host == "api.atlassian.com"
    assert requests[-1].headers["Authorization"] == "Bearer access-2"
    assert oauth.jira_api_url("cloud-123").endswith("/ex/jira/cloud-123")


def test_oauth_fails_safely_when_configuration_or_offline_access_is_missing() -> None:
    with pytest.raises(JiraError, match="JIRA_OAUTH_CLIENT_ID"):
        AtlassianOAuthClient(None, None, None).authorization_url("state")

    oauth = AtlassianOAuthClient(
        "client-id",
        "client-secret",
        "https://tickettalk.io/jira/oauth/callback",
        transport=httpx.MockTransport(
            lambda _: httpx.Response(200, json={"access_token": "access"})
        ),
    )
    with pytest.raises(JiraError, match="offline access"):
        oauth.exchange_code("authorization-code")

    invalid_lifetime = AtlassianOAuthClient(
        "client-id",
        "client-secret",
        "https://tickettalk.io/jira/oauth/callback",
        transport=httpx.MockTransport(
            lambda _: httpx.Response(
                200,
                json={
                    "access_token": "access",
                    "refresh_token": "refresh",
                    "expires_in": "later",
                },
            )
        ),
    )
    with pytest.raises(JiraError, match="token lifetime"):
        invalid_lifetime.exchange_code("authorization-code")
