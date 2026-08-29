import base64
from collections.abc import Iterable
from datetime import datetime
from typing import Any, Self

import httpx
from cryptography.fernet import Fernet, InvalidToken

from .models import JiraField, JiraImportRow, JiraUser

MAX_JIRA_TICKETS = 500
SEARCH_PAGE_SIZE = 100


class JiraError(Exception):
    """A Jira failure safe to show to the facilitator."""


class TokenCipher:
    def __init__(self, key: str) -> None:
        try:
            self.fernet = Fernet(key.encode())
        except (TypeError, ValueError) as error:
            raise ValueError("JIRA_ENCRYPTION_KEY must be a valid Fernet key") from error

    def encrypt(self, token: str) -> str:
        return self.fernet.encrypt(token.encode()).decode()

    def decrypt(self, encrypted_token: str) -> str:
        try:
            return self.fernet.decrypt(encrypted_token.encode()).decode()
        except InvalidToken as error:
            raise JiraError("The stored Jira credential cannot be decrypted; reconnect Jira") from error


def generate_encryption_key() -> str:
    return Fernet.generate_key().decode()


def _adf_text(value: Any) -> str:
    if isinstance(value, str):
        return value
    if isinstance(value, list):
        return "".join(_adf_text(item) for item in value)
    if not isinstance(value, dict):
        return ""
    text = str(value.get("text") or "")
    children = _adf_text(value.get("content") or [])
    suffix = "\n" if value.get("type") in {"paragraph", "heading", "listItem"} else ""
    return f"{text}{children}{suffix}"


def _avatar(user: dict[str, Any]) -> str | None:
    avatars = user.get("avatarUrls") or {}
    return avatars.get("24x24") or avatars.get("48x48")


class JiraClient:
    def __init__(
        self,
        site_url: str,
        email: str,
        api_token: str,
        *,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        authorization = base64.b64encode(f"{email}:{api_token}".encode()).decode()
        self.client = httpx.Client(
            base_url=site_url,
            headers={
                "Accept": "application/json",
                "Authorization": f"Basic {authorization}",
                "User-Agent": "tickettalk-jira/0.1",
            },
            timeout=httpx.Timeout(20, connect=10),
            follow_redirects=False,
            transport=transport,
        )

    def __enter__(self) -> Self:
        return self

    def __exit__(self, *_: object) -> None:
        self.client.close()

    @staticmethod
    def _error(response: httpx.Response) -> JiraError:
        if response.status_code == 401:
            return JiraError("Jira rejected the email or API token")
        if response.status_code == 403:
            return JiraError("The Jira account does not have permission for this action")
        if response.status_code == 429:
            wait = response.headers.get("Retry-After")
            suffix = f" Retry after {wait} seconds." if wait else ""
            return JiraError(f"Jira rate-limited the request.{suffix}")
        try:
            payload = response.json()
        except ValueError:
            payload = {}
        messages = payload.get("errorMessages") or []
        field_errors = (payload.get("errors") or {}).values()
        detail = " ".join(str(item) for item in [*messages, *field_errors] if item)
        return JiraError(detail or f"Jira request failed with status {response.status_code}")

    def _request(self, method: str, path: str, **kwargs: Any) -> httpx.Response:
        try:
            response = self.client.request(method, path, **kwargs)
        except httpx.RequestError as error:
            raise JiraError("Jira could not be reached") from error
        if response.is_error:
            raise self._error(response)
        return response

    def myself(self) -> dict[str, str]:
        data = self._request("GET", "/rest/api/3/myself").json()
        return {
            "account_id": str(data["accountId"]),
            "display_name": str(data.get("displayName") or "Jira user"),
        }

    def story_points_fields(self) -> list[JiraField]:
        fields = self._request("GET", "/rest/api/3/field").json()
        candidates = []
        for field in fields:
            name = str(field.get("name") or "")
            custom = str((field.get("schema") or {}).get("custom") or "")
            normalized = name.casefold().replace("_", " ")
            if "story point" in normalized or custom.endswith(":float") and "point" in normalized:
                candidates.append(JiraField(id=str(field["id"]), name=name))
        return sorted(candidates, key=lambda item: item.name.casefold())

    def search(self, jql: str, story_points_field_id: str | None) -> list[JiraImportRow]:
        requested_fields = [
            "summary",
            "issuetype",
            "description",
            "assignee",
            "updated",
        ]
        if story_points_field_id:
            requested_fields.append(story_points_field_id)
        issues: list[dict[str, Any]] = []
        next_page_token: str | None = None
        while True:
            body: dict[str, Any] = {
                "jql": jql,
                "fields": requested_fields,
                "maxResults": SEARCH_PAGE_SIZE,
            }
            if next_page_token:
                body["nextPageToken"] = next_page_token
            page = self._request("POST", "/rest/api/3/search/jql", json=body).json()
            issues.extend(page.get("issues") or [])
            next_page_token = page.get("nextPageToken")
            if len(issues) > MAX_JIRA_TICKETS or next_page_token and len(issues) >= MAX_JIRA_TICKETS:
                raise JiraError("The JQL query returns more than 500 tickets; narrow the query")
            if not next_page_token:
                break

        rows: list[JiraImportRow] = []
        for index, issue in enumerate(issues, start=1):
            fields = issue.get("fields") or {}
            assignee = fields.get("assignee") or {}
            points = fields.get(story_points_field_id) if story_points_field_id else None
            updated = fields.get("updated")
            rows.append(
                JiraImportRow(
                    row_number=index,
                    issue_key=str(issue["key"]),
                    summary=str(fields.get("summary") or issue["key"]),
                    issue_type=str((fields.get("issuetype") or {}).get("name") or "Story"),
                    description=_adf_text(fields.get("description")).strip(),
                    story_points=float(points) if points is not None else None,
                    jira_issue_id=str(issue["id"]),
                    jira_updated_at=datetime.fromisoformat(updated) if updated else None,
                    jira_assignee_account_id=assignee.get("accountId"),
                    jira_assignee_display_name=assignee.get("displayName"),
                    final_assignee_account_id=assignee.get("accountId"),
                    final_assignee_display_name=assignee.get("displayName"),
                )
            )
        return rows

    def assignable_users(self, issue_key: str, query: str = "") -> list[JiraUser]:
        response = self._request(
            "GET",
            "/rest/api/3/user/assignable/search",
            params={"issueKey": issue_key, "query": query, "maxResults": 50},
        )
        return [
            JiraUser(
                account_id=str(user["accountId"]),
                display_name=str(user.get("displayName") or "Jira user"),
                avatar_url=_avatar(user),
            )
            for user in response.json()
            if user.get("active", True) and user.get("accountId")
        ]

    def write_issue(
        self,
        issue_key: str,
        story_points_field_id: str,
        final_estimate: float,
        assignee_account_id: str | None,
    ) -> None:
        self._request(
            "PUT",
            f"/rest/api/3/issue/{issue_key}",
            headers={"Content-Type": "application/json"},
            json={
                "fields": {
                    story_points_field_id: final_estimate,
                    "assignee": (
                        {"accountId": assignee_account_id}
                        if assignee_account_id
                        else None
                    ),
                }
            },
        )


def field_ids(fields: Iterable[JiraField]) -> set[str]:
    return {field.id for field in fields}
