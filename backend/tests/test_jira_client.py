import json

import httpx
import pytest
from cryptography.fernet import Fernet

from app.jira_client import JiraClient, JiraError, TokenCipher, generate_encryption_key
from app.models import JiraConnectionCreate


def test_connection_restricts_hosts_and_token_cipher_round_trips() -> None:
    connection = JiraConnectionCreate(
        site_url="https://example.atlassian.net/",
        email=" User@Example.com ",
        api_token="secret",
    )
    cipher = TokenCipher(generate_encryption_key())
    encrypted = cipher.encrypt(connection.api_token)

    assert connection.site_url == "https://example.atlassian.net"
    assert connection.email == "user@example.com"
    assert encrypted != connection.api_token
    assert cipher.decrypt(encrypted) == connection.api_token

    for site_url in (
        "http://example.atlassian.net",
        "https://atlassian.net.evil.test",
        "https://example.atlassian.net/path",
        "https://127.0.0.1",
    ):
        with pytest.raises(ValueError):
            JiraConnectionCreate(
                site_url=site_url,
                email="user@example.com",
                api_token="secret",
            )

    with pytest.raises(ValueError, match="valid Fernet key"):
        TokenCipher("invalid")
    with pytest.raises(JiraError, match="cannot be decrypted"):
        cipher.decrypt(Fernet.generate_key().decode())


def test_client_reads_paginated_jql_adf_assignees_and_writes_fields() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if request.url.path == "/rest/api/3/search/jql":
            body = json.loads(request.content)
            page = body.get("nextPageToken")
            issue_number = 2 if page else 1
            return httpx.Response(
                200,
                json={
                    "issues": [
                        {
                            "id": str(10000 + issue_number),
                            "key": f"PAY-{issue_number}",
                            "fields": {
                                "summary": f"Ticket {issue_number}",
                                "issuetype": {"name": "Story"},
                                "description": {
                                    "type": "doc",
                                    "content": [
                                        {
                                            "type": "paragraph",
                                            "content": [{"type": "text", "text": "Context"}],
                                        }
                                    ],
                                },
                                "customfield_10016": 5,
                                "updated": "2026-08-29T10:00:00+00:00",
                                "assignee": {
                                    "accountId": "account-1",
                                    "displayName": "Maya",
                                },
                            },
                        }
                    ],
                    **({"nextPageToken": "page-2"} if not page else {}),
                },
            )
        if request.url.path == "/rest/api/3/user/assignable/search":
            return httpx.Response(
                200,
                json=[
                    {
                        "accountId": "account-2",
                        "displayName": "Alex",
                        "active": True,
                        "avatarUrls": {"24x24": "https://avatar.test/alex.png"},
                    }
                ],
            )
        if request.url.path == "/rest/api/3/issue/PAY-1":
            return httpx.Response(204)
        return httpx.Response(404)

    with JiraClient(
        "https://example.atlassian.net",
        "user@example.com",
        "secret",
        transport=httpx.MockTransport(handler),
    ) as jira:
        rows = jira.search("project = PAY", "customfield_10016")
        users = jira.assignable_users("PAY-1", "Alex")
        jira.write_issue("PAY-1", "customfield_10016", 8, "account-2")

    assert [row.issue_key for row in rows] == ["PAY-1", "PAY-2"]
    assert rows[0].description == "Context"
    assert rows[0].story_points == 5
    assert users[0].display_name == "Alex"
    assert requests[0].headers["Authorization"].startswith("Basic ")
    write_body = json.loads(requests[-1].content)
    assert write_body["fields"] == {
        "customfield_10016": 8,
        "assignee": {"accountId": "account-2"},
    }


def test_client_returns_safe_jira_errors() -> None:
    transport = httpx.MockTransport(
        lambda _: httpx.Response(400, json={"errorMessages": ["Invalid JQL"]})
    )
    with (
        JiraClient(
            "https://example.atlassian.net",
            "user@example.com",
            "secret",
            transport=transport,
        ) as jira,
        pytest.raises(JiraError, match="Invalid JQL"),
    ):
        jira.search("invalid", None)


@pytest.mark.parametrize(
    ("status", "headers", "message"),
    [
        (401, {}, "rejected the email or API token"),
        (403, {}, "does not have permission"),
        (429, {"Retry-After": "12"}, "Retry after 12 seconds"),
        (500, {}, "status 500"),
    ],
)
def test_client_normalizes_auth_rate_limit_and_server_errors(
    status: int, headers: dict[str, str], message: str
) -> None:
    transport = httpx.MockTransport(
        lambda _: httpx.Response(status, headers=headers, text="internal details")
    )
    with (
        JiraClient(
            "https://example.atlassian.net",
            "user@example.com",
            "secret",
            transport=transport,
        ) as jira,
        pytest.raises(JiraError, match=message),
    ):
        jira.myself()


def test_client_normalizes_network_errors() -> None:
    def unavailable(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("private network detail", request=request)

    with (
        JiraClient(
            "https://example.atlassian.net",
            "user@example.com",
            "secret",
            transport=httpx.MockTransport(unavailable),
        ) as jira,
        pytest.raises(JiraError, match="could not be reached"),
    ):
        jira.myself()
