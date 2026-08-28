import os

import pytest
from fastapi.testclient import TestClient
from supabase import create_client

from app.auth import SupabaseAuthenticator, get_authenticator
from app.main import app, get_repository
from app.repositories import SupabaseRepository

SUPABASE_URL = os.getenv("SUPABASE_INTEGRATION_URL")
SUPABASE_ANON_KEY = os.getenv("SUPABASE_INTEGRATION_ANON_KEY")
SUPABASE_SECRET_KEY = os.getenv("SUPABASE_INTEGRATION_SECRET_KEY")

pytestmark = pytest.mark.skipif(
    not all((SUPABASE_URL, SUPABASE_ANON_KEY, SUPABASE_SECRET_KEY)),
    reason="local Supabase integration credentials are not configured",
)


def test_real_supabase_clients_persist_and_protect_the_backlog() -> None:
    service = create_client(SUPABASE_URL or "", SUPABASE_SECRET_KEY or "")
    owner_auth = create_client(SUPABASE_URL or "", SUPABASE_ANON_KEY or "")
    member_auth = create_client(SUPABASE_URL or "", SUPABASE_ANON_KEY or "")
    owner_session = owner_auth.auth.sign_in_anonymously(
        {"options": {"data": {"display_name": "Integration owner"}}}
    )
    member_session = member_auth.auth.sign_in_anonymously(
        {"options": {"data": {"display_name": "Integration member"}}}
    )
    owner = owner_session.user
    member = member_session.user
    assert owner and member and owner_session.session and member_session.session

    app.dependency_overrides[get_authenticator] = lambda: SupabaseAuthenticator(
        SUPABASE_URL or "", SUPABASE_SECRET_KEY or ""
    )
    app.dependency_overrides[get_repository] = lambda: SupabaseRepository(
        SUPABASE_URL or "", SUPABASE_SECRET_KEY or ""
    )
    client = TestClient(app)
    owner_headers = {"Authorization": f"Bearer {owner_session.session.access_token}"}
    member_headers = {"Authorization": f"Bearer {member_session.session.access_token}"}

    try:
        room = client.post(
            "/api/rooms",
            json={"name": "Supabase backlog integration"},
            headers=owner_headers,
        ).json()
        room_id = room["id"]
        content = "Issue key,Summary,Story Points\nINT-1,Imported ticket,8\n"
        preview = client.post(
            f"/api/rooms/{room_id}/tickets/import/preview",
            json={"content": content, "duplicate_behavior": "error"},
            headers=owner_headers,
        )
        assert preview.status_code == 200
        assert preview.json()["saved_count"] == 1

        imported = client.post(
            f"/api/rooms/{room_id}/tickets/import",
            json={"content": content, "duplicate_behavior": "error"},
            headers=owner_headers,
        )
        assert imported.status_code == 200
        assert imported.json()["tickets"][0]["story_points"] == 8

        replacement_content = (
            "Issue key,Summary,Story Points\nINT-1,Updated imported ticket,13\n"
        )
        replacement_preview = client.post(
            f"/api/rooms/{room_id}/tickets/import/preview",
            json={"content": replacement_content, "duplicate_behavior": "replace"},
            headers=owner_headers,
        ).json()
        assert replacement_preview["rows"][0]["action"] == "replace"
        replacement = client.post(
            f"/api/rooms/{room_id}/tickets/import",
            json={"content": replacement_content, "duplicate_behavior": "replace"},
            headers=owner_headers,
        )
        assert replacement.status_code == 200
        assert replacement.json()["replaced_count"] == 1
        assert replacement.json()["tickets"][0]["story_points"] == 13

        manual = client.post(
            f"/api/rooms/{room_id}/tickets",
            json={"summary": "Manual integration ticket"},
            headers=owner_headers,
        )
        assert manual.status_code == 201
        assert manual.json()["issue_key"] is None

        refreshed = client.get(
            f"/api/rooms/{room_id}/tickets", headers=owner_headers
        ).json()
        assert [ticket["summary"] for ticket in refreshed] == [
            "Updated imported ticket",
            "Manual integration ticket",
        ]

        joined = client.post(
            f"/api/rooms/{room_id}/join",
            json={"display_name": "Integration member"},
            headers=member_headers,
        )
        assert joined.status_code == 200

        first_ticket_id = refreshed[0]["id"]
        manual_ticket_id = manual.json()["id"]
        activated = client.patch(
            f"/api/rooms/{room_id}/active-ticket",
            json={"ticket_id": first_ticket_id},
            headers=owner_headers,
        )
        assert activated.status_code == 200
        assert activated.json()["active_ticket_id"] == first_ticket_id
        member_room = client.get(
            f"/api/rooms/{room_id}", headers=member_headers
        )
        assert member_room.status_code == 200
        assert member_room.json()["active_ticket_id"] == first_ticket_id

        denied_navigation = client.patch(
            f"/api/rooms/{room_id}/active-ticket",
            json={"ticket_id": manual_ticket_id},
            headers=member_headers,
        )
        assert denied_navigation.status_code == 403

        rapid_navigation = client.patch(
            f"/api/rooms/{room_id}/active-ticket",
            json={"ticket_id": manual_ticket_id},
            headers=owner_headers,
        )
        assert rapid_navigation.status_code == 200
        reordered = client.put(
            f"/api/rooms/{room_id}/tickets/order",
            json={"ticket_ids": [manual_ticket_id, first_ticket_id]},
            headers=owner_headers,
        )
        assert reordered.status_code == 200
        reconnected = client.get(f"/api/rooms/{room_id}", headers=member_headers)
        assert reconnected.json()["active_ticket_id"] == manual_ticket_id

        denied = client.post(
            f"/api/rooms/{room_id}/tickets",
            json={"summary": "Member mutation"},
            headers=member_headers,
        )
        assert denied.status_code == 403
    finally:
        app.dependency_overrides.clear()
        service.auth.admin.delete_user(str(owner.id))
        service.auth.admin.delete_user(str(member.id))
