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
        assert repository.members[UUID(room["id"])][OWNER.id] == "facilitator"

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
