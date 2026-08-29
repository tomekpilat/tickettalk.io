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
