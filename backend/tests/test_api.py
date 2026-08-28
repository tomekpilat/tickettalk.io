from datetime import UTC, datetime, timedelta
from uuid import UUID

from fastapi.testclient import TestClient

from app.auth import Principal, get_current_principal
from app.main import app, get_repository
from app.repositories import InMemoryRepository

OWNER = Principal(
    id=UUID("00000000-0000-0000-0000-000000000001"),
    email="owner@example.com",
    display_name="Owner",
)
OUTSIDER = Principal(
    id=UUID("00000000-0000-0000-0000-000000000002"),
    email="outsider@example.com",
    display_name="Outsider",
)
MEMBER_A = Principal(
    id=UUID("00000000-0000-0000-0000-000000000003"),
    display_name="Sam",
    is_anonymous=True,
)
MEMBER_B = Principal(
    id=UUID("00000000-0000-0000-0000-000000000004"),
    display_name="Sam",
    is_anonymous=True,
)


def client_with(repository: InMemoryRepository, actor: Principal = OWNER) -> TestClient:
    app.dependency_overrides[get_repository] = lambda: repository
    app.dependency_overrides[get_current_principal] = lambda: actor
    return TestClient(app)


def clear_overrides() -> None:
    app.dependency_overrides.clear()


def test_room_creation_is_owned_and_uses_uuid() -> None:
    repository = InMemoryRepository(seed=False)
    client = client_with(repository)
    try:
        response = client.post(
            "/api/rooms",
            json={"name": "  Sprint   43  ", "scale": "extended", "reveal_mode": "auto"},
        )
        assert response.status_code == 201
        room = response.json()
        UUID(room["id"])
        assert room["owner_id"] == str(OWNER.id)
        assert room["name"] == "Sprint 43"
        assert repository.members[UUID(room["id"])][OWNER.id].role == "facilitator"

        fetched = client.get(f"/api/rooms/{room['id']}")
        assert fetched.status_code == 200
        assert fetched.json()["scale"] == "extended"
    finally:
        clear_overrides()


def test_room_settings_are_owner_only() -> None:
    repository = InMemoryRepository(seed=False)
    owner_client = client_with(repository)
    room = owner_client.post("/api/rooms", json={"name": "Sprint planning"}).json()

    app.dependency_overrides[get_current_principal] = lambda: OUTSIDER
    outsider_client = TestClient(app)
    try:
        assert outsider_client.get(f"/api/rooms/{room['id']}").status_code == 403
        assert (
            outsider_client.patch(
                f"/api/rooms/{room['id']}", json={"name": "Hijacked room"}
            ).status_code
            == 403
        )

        app.dependency_overrides[get_current_principal] = lambda: OWNER
        updated = owner_client.patch(
            f"/api/rooms/{room['id']}",
            json={"name": "Sprint 44", "scale": "tshirt", "reveal_mode": "auto"},
        )
        assert updated.status_code == 200
        assert updated.json()["name"] == "Sprint 44"
        assert updated.json()["scale"] == "tshirt"
    finally:
        clear_overrides()


def test_room_validation_and_authentication() -> None:
    repository = InMemoryRepository(seed=False)
    app.dependency_overrides[get_repository] = lambda: repository
    unauthenticated = TestClient(app)
    try:
        assert unauthenticated.get("/api/rooms").status_code == 401
    finally:
        clear_overrides()

    client = client_with(repository)
    try:
        assert client.post("/api/rooms", json={"name": "x"}).status_code == 422
        assert (
            client.post(
                "/api/rooms", json={"name": "Valid room", "scale": "powers-of-two"}
            ).status_code
            == 422
        )
    finally:
        clear_overrides()


def test_ticket_estimate_flow_requires_owner() -> None:
    repository = InMemoryRepository()
    client = client_with(repository)
    try:
        rooms = client.get("/api/rooms").json()
        room_id = rooms[0]["id"]
        tickets = client.get(f"/api/rooms/{room_id}/tickets").json()
        response = client.patch(
            f"/api/tickets/{tickets[2]['id']}/estimate", json={"story_points": 8}
        )
        assert response.status_code == 200
        assert response.json()["story_points"] == 8
    finally:
        clear_overrides()


def test_two_anonymous_clients_join_once_with_distinct_identities() -> None:
    repository = InMemoryRepository(seed=False)
    client = client_with(repository)
    room = client.post("/api/rooms", json={"name": "Shared planning"}).json()
    room_id = room["id"]
    try:
        app.dependency_overrides[get_current_principal] = lambda: MEMBER_A
        first_join = client.post(
            f"/api/rooms/{room_id}/join", json={"display_name": " Sam "}
        )
        reconnect = client.post(
            f"/api/rooms/{room_id}/join", json={"display_name": "Sam"}
        )
        assert first_join.status_code == 200
        assert reconnect.status_code == 200
        assert first_join.json()["user_id"] == reconnect.json()["user_id"]

        app.dependency_overrides[get_current_principal] = lambda: MEMBER_B
        second_join = client.post(
            f"/api/rooms/{room_id}/join", json={"display_name": "Sam"}
        )
        assert second_join.status_code == 200
        assert second_join.json()["user_id"] != first_join.json()["user_id"]

        members = client.get(f"/api/rooms/{room_id}/members")
        assert members.status_code == 200
        assert len(members.json()) == 3
        assert all("value" not in member for member in members.json())

        app.dependency_overrides[get_current_principal] = lambda: OUTSIDER
        assert client.get(f"/api/rooms/{room_id}/members").status_code == 403
        assert client.get(f"/api/rooms/{room_id}/tickets").status_code == 403
    finally:
        clear_overrides()


def test_presence_heartbeat_recovers_a_disconnected_member() -> None:
    repository = InMemoryRepository(seed=False)
    client = client_with(repository)
    room_id = client.post("/api/rooms", json={"name": "Presence room"}).json()["id"]
    room_uuid = UUID(room_id)
    try:
        app.dependency_overrides[get_current_principal] = lambda: MEMBER_A
        client.post(f"/api/rooms/{room_id}/join", json={"display_name": "Sam"})
        repository.members[room_uuid][MEMBER_A.id].last_seen_at = (
            datetime.now(UTC) - timedelta(minutes=2)
        )

        app.dependency_overrides[get_current_principal] = lambda: OWNER
        stale = client.get(f"/api/rooms/{room_id}/members").json()
        assert next(item for item in stale if item["user_id"] == str(MEMBER_A.id))[
            "is_online"
        ] is False

        app.dependency_overrides[get_current_principal] = lambda: MEMBER_A
        heartbeat = client.post(f"/api/rooms/{room_id}/presence")
        assert heartbeat.status_code == 200
        assert heartbeat.json()["is_online"] is True

        app.dependency_overrides[get_current_principal] = lambda: OWNER
        refreshed = client.get(f"/api/rooms/{room_id}/members").json()
        assert next(item for item in refreshed if item["user_id"] == str(MEMBER_A.id))[
            "is_online"
        ] is True
    finally:
        clear_overrides()


def test_jira_preview_save_and_manual_backlog_persist_in_order() -> None:
    repository = InMemoryRepository(seed=False)
    client = client_with(repository)
    room_id = client.post("/api/rooms", json={"name": "Backlog room"}).json()["id"]
    csv_content = (
        "Issue key,Summary,Issue Type,Description,Story Points\n"
        'PAY-51,"Checkout, safely",Story,"First line\nSecond line",5\n'
        "PAY-52,Retry webhook,Bug,Retry failed deliveries,\n"
    )
    try:
        preview = client.post(
            f"/api/rooms/{room_id}/tickets/import/preview",
            json={"content": csv_content, "duplicate_behavior": "error"},
        )
        assert preview.status_code == 200
        assert preview.json()["source_count"] == 2
        assert preview.json()["saved_count"] == 2
        assert preview.json()["errors"] == []

        saved = client.post(
            f"/api/rooms/{room_id}/tickets/import",
            json={"content": csv_content, "duplicate_behavior": "error"},
        )
        assert saved.status_code == 200
        assert saved.json()["imported_count"] == preview.json()["saved_count"]
        assert [ticket["issue_key"] for ticket in saved.json()["tickets"]] == [
            "PAY-51",
            "PAY-52",
        ]
        assert saved.json()["tickets"][0]["description"] == "First line\nSecond line"

        manual = client.post(
            f"/api/rooms/{room_id}/tickets",
            json={
                "summary": "Untracked product question",
                "issue_type": "Discussion",
                "description": "Decide the smallest useful scope.",
            },
        )
        assert manual.status_code == 201
        assert manual.json()["issue_key"] is None

        edited = client.patch(
            f"/api/rooms/{room_id}/tickets/{manual.json()['id']}",
            json={"summary": "Clarify product question", "issue_key": "TT-LOCAL"},
        )
        assert edited.status_code == 200

        current = client.get(f"/api/rooms/{room_id}/tickets").json()
        reverse_order = [ticket["id"] for ticket in reversed(current)]
        reordered = client.put(
            f"/api/rooms/{room_id}/tickets/order", json={"ticket_ids": reverse_order}
        )
        assert [ticket["id"] for ticket in reordered.json()] == reverse_order

        removed_id = reordered.json()[1]["id"]
        assert client.delete(
            f"/api/rooms/{room_id}/tickets/{removed_id}"
        ).status_code == 204
        refreshed = client.get(f"/api/rooms/{room_id}/tickets").json()
        assert [ticket["position"] for ticket in refreshed] == [0, 1]
        assert [ticket["id"] for ticket in refreshed] == [
            reverse_order[0],
            reverse_order[2],
        ]
    finally:
        clear_overrides()


def test_members_cannot_preview_or_mutate_the_backlog() -> None:
    repository = InMemoryRepository(seed=False)
    client = client_with(repository)
    room_id = client.post("/api/rooms", json={"name": "Protected backlog"}).json()["id"]
    try:
        app.dependency_overrides[get_current_principal] = lambda: MEMBER_A
        client.post(f"/api/rooms/{room_id}/join", json={"display_name": "Sam"})
        payload = {"content": "Summary\nPrivate import\n", "duplicate_behavior": "error"}
        assert client.post(
            f"/api/rooms/{room_id}/tickets/import/preview", json=payload
        ).status_code == 403
        assert client.post(
            f"/api/rooms/{room_id}/tickets", json={"summary": "Unauthorized"}
        ).status_code == 403
    finally:
        clear_overrides()


def test_active_ticket_navigation_is_shared_owner_only_and_stable() -> None:
    repository = InMemoryRepository(seed=False)
    client = client_with(repository)
    room_id = client.post("/api/rooms", json={"name": "Synchronized session"}).json()[
        "id"
    ]
    tickets = [
        client.post(
            f"/api/rooms/{room_id}/tickets", json={"summary": f"Ticket {index}"}
        ).json()
        for index in range(1, 4)
    ]
    try:
        first = client.patch(
            f"/api/rooms/{room_id}/active-ticket",
            json={"ticket_id": tickets[0]["id"]},
        )
        assert first.status_code == 200
        assert first.json()["active_ticket_id"] == tickets[0]["id"]

        app.dependency_overrides[get_current_principal] = lambda: MEMBER_A
        client.post(f"/api/rooms/{room_id}/join", json={"display_name": "Sam"})
        assert client.get(f"/api/rooms/{room_id}").json()["active_ticket_id"] == tickets[0][
            "id"
        ]
        assert client.patch(
            f"/api/rooms/{room_id}/active-ticket",
            json={"ticket_id": tickets[1]["id"]},
        ).status_code == 403

        app.dependency_overrides[get_current_principal] = lambda: OWNER
        for ticket in tickets[1:]:
            assert client.patch(
                f"/api/rooms/{room_id}/active-ticket",
                json={"ticket_id": ticket["id"]},
            ).status_code == 200

        reversed_ids = [ticket["id"] for ticket in reversed(tickets)]
        client.put(
            f"/api/rooms/{room_id}/tickets/order", json={"ticket_ids": reversed_ids}
        )
        assert client.get(f"/api/rooms/{room_id}").json()["active_ticket_id"] == tickets[2][
            "id"
        ]

        client.delete(f"/api/rooms/{room_id}/tickets/{tickets[2]['id']}")
        assert client.get(f"/api/rooms/{room_id}").json()["active_ticket_id"] == tickets[1][
            "id"
        ]

        app.dependency_overrides[get_current_principal] = lambda: MEMBER_A
        reconnect = client.get(f"/api/rooms/{room_id}")
        assert reconnect.status_code == 200
        assert reconnect.json()["active_ticket_id"] == tickets[1]["id"]
    finally:
        clear_overrides()
