from fastapi.testclient import TestClient

from app.main import app, get_repository
from app.repositories import InMemoryRepository


def test_room_and_estimate_flow() -> None:
    repository = InMemoryRepository()
    app.dependency_overrides[get_repository] = lambda: repository
    client = TestClient(app)

    assert client.get("/health").json() == {"status": "ok"}
    rooms = client.get("/api/rooms").json()
    assert rooms[0]["name"] == "Sprint 42 · Checkout"

    tickets = client.get("/api/rooms/demo-room/tickets").json()
    response = client.patch(f"/api/tickets/{tickets[2]['id']}/estimate", json={"story_points": 8})
    assert response.status_code == 200
    assert response.json()["story_points"] == 8

    app.dependency_overrides.clear()

