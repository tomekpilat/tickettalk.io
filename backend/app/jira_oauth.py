from datetime import UTC, datetime, timedelta
from typing import Any
from urllib.parse import urlencode

import httpx
from pydantic import BaseModel

from .jira_client import JiraError

ATLASSIAN_AUTH_URL = "https://auth.atlassian.com/authorize"
ATLASSIAN_TOKEN_URL = "https://auth.atlassian.com/oauth/token"
ATLASSIAN_API_URL = "https://api.atlassian.com"
JIRA_OAUTH_SCOPES = "read:jira-work read:jira-user write:jira-work offline_access"


class JiraOAuthTokens(BaseModel):
    access_token: str
    refresh_token: str
    expires_at: datetime


class JiraOAuthResource(BaseModel):
    id: str
    url: str
    name: str


class AtlassianOAuthClient:
    def __init__(
        self,
        client_id: str | None,
        client_secret: str | None,
        redirect_uri: str | None,
        *,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self.client_id = client_id
        self.client_secret = client_secret
        self.redirect_uri = redirect_uri
        self.transport = transport

    def _require_config(self) -> tuple[str, str, str]:
        if not (self.client_id and self.client_secret and self.redirect_uri):
            raise JiraError(
                "Jira OAuth is not configured; set JIRA_OAUTH_CLIENT_ID, "
                "JIRA_OAUTH_CLIENT_SECRET, and JIRA_OAUTH_REDIRECT_URI"
            )
        return self.client_id, self.client_secret, self.redirect_uri

    def authorization_url(self, state: str) -> str:
        client_id, _, redirect_uri = self._require_config()
        query = urlencode(
            {
                "audience": "api.atlassian.com",
                "client_id": client_id,
                "scope": JIRA_OAUTH_SCOPES,
                "redirect_uri": redirect_uri,
                "state": state,
                "response_type": "code",
                "prompt": "consent",
            }
        )
        return f"{ATLASSIAN_AUTH_URL}?{query}"

    def exchange_code(self, code: str) -> JiraOAuthTokens:
        client_id, client_secret, redirect_uri = self._require_config()
        return self._tokens(
            {
                "grant_type": "authorization_code",
                "client_id": client_id,
                "client_secret": client_secret,
                "code": code,
                "redirect_uri": redirect_uri,
            }
        )

    def refresh(self, refresh_token: str) -> JiraOAuthTokens:
        client_id, client_secret, _ = self._require_config()
        return self._tokens(
            {
                "grant_type": "refresh_token",
                "client_id": client_id,
                "client_secret": client_secret,
                "refresh_token": refresh_token,
            }
        )

    def _tokens(self, payload: dict[str, str]) -> JiraOAuthTokens:
        data = self._request("POST", ATLASSIAN_TOKEN_URL, json=payload)
        access_token = str(data.get("access_token") or "")
        refresh_token = str(data.get("refresh_token") or "")
        if not access_token or not refresh_token:
            raise JiraError("Atlassian did not return offline access; connect Jira again")
        try:
            expires_in = int(data.get("expires_in") or 3600)
        except (TypeError, ValueError) as error:
            raise JiraError("Atlassian returned an invalid token lifetime") from error
        return JiraOAuthTokens(
            access_token=access_token,
            refresh_token=refresh_token,
            expires_at=datetime.now(UTC) + timedelta(seconds=expires_in),
        )

    def accessible_resources(self, access_token: str) -> list[JiraOAuthResource]:
        data = self._request(
            "GET",
            f"{ATLASSIAN_API_URL}/oauth/token/accessible-resources",
            headers={"Authorization": f"Bearer {access_token}"},
        )
        if not isinstance(data, list):
            raise JiraError("Atlassian returned an invalid list of Jira sites")
        return [JiraOAuthResource.model_validate(item) for item in data]

    def _request(self, method: str, path: str, **kwargs: Any) -> Any:
        try:
            with httpx.Client(
                timeout=httpx.Timeout(20, connect=10),
                transport=self.transport,
            ) as client:
                response = client.request(method, path, **kwargs)
        except httpx.RequestError as error:
            raise JiraError("Atlassian authorization could not be reached") from error
        if response.is_error:
            raise JiraError("Atlassian rejected the authorization request; connect again")
        try:
            return response.json()
        except ValueError as error:
            raise JiraError("Atlassian returned an invalid authorization response") from error

    @staticmethod
    def jira_api_url(cloud_id: str) -> str:
        return f"{ATLASSIAN_API_URL}/ex/jira/{cloud_id}"
