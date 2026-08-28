import csv
import io
import os
from concurrent.futures import ThreadPoolExecutor

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

        owner_vote = client.put(
            f"/api/rooms/{room_id}/tickets/{manual_ticket_id}/vote",
            json={"value": "5"},
            headers=owner_headers,
        )
        member_vote = client.put(
            f"/api/rooms/{room_id}/tickets/{manual_ticket_id}/vote",
            json={"value": "8"},
            headers=member_headers,
        )
        assert owner_vote.status_code == member_vote.status_code == 200
        assert "value" not in owner_vote.json()
        assert "value" not in member_vote.json()
        roster = client.get(
            f"/api/rooms/{room_id}/members", headers=member_headers
        ).json()
        assert len([person for person in roster if person["has_voted"]]) == 2

        owner_direct_votes = (
            owner_auth.table("votes")
            .select("user_id,value")
            .eq("ticket_id", manual_ticket_id)
            .execute()
        )
        assert len(owner_direct_votes.data) == 1
        assert owner_direct_votes.data[0]["user_id"] == str(owner.id)
        safe_statuses = (
            owner_auth.table("vote_statuses")
            .select("user_id")
            .eq("ticket_id", manual_ticket_id)
            .execute()
        )
        assert len(safe_statuses.data) == 2

        denied_reveal = client.post(
            f"/api/rooms/{room_id}/tickets/{manual_ticket_id}/reveal",
            headers=member_headers,
        )
        assert denied_reveal.status_code == 403
        with ThreadPoolExecutor(max_workers=2) as executor:
            revealed, duplicate_reveal = list(
                executor.map(
                    lambda _index: client.post(
                        f"/api/rooms/{room_id}/tickets/{manual_ticket_id}/reveal",
                        headers=owner_headers,
                    ),
                    range(2),
                )
            )
        assert revealed.status_code == duplicate_reveal.status_code == 200
        assert revealed.json()["state"] == "revealed"
        assert len(revealed.json()["votes"]) == 2
        assert duplicate_reveal.json()["votes"] == revealed.json()["votes"]
        member_results = client.get(
            f"/api/rooms/{room_id}/tickets/{manual_ticket_id}/votes",
            headers=member_headers,
        )
        assert member_results.json()["votes"] == revealed.json()["votes"]
        assert client.put(
            f"/api/rooms/{room_id}/tickets/{manual_ticket_id}/final-estimate",
            json={"value": "8"},
            headers=member_headers,
        ).status_code == 403
        final_estimate = client.put(
            f"/api/rooms/{room_id}/tickets/{manual_ticket_id}/final-estimate",
            json={"value": "8"},
            headers=owner_headers,
        )
        assert final_estimate.status_code == 200
        assert final_estimate.json()["final_estimate"] == "8"
        exported = client.get(f"/api/rooms/{room_id}/export", headers=owner_headers)
        assert exported.status_code == 200
        export_rows = list(csv.reader(io.StringIO(exported.text)))
        manual_export = next(
            row for row in export_rows[1:] if row[1] == "Manual integration ticket"
        )
        assert manual_export[-1] == "8"
        assert client.get(
            f"/api/rooms/{room_id}/export", headers=member_headers
        ).status_code == 403

        restarted = client.post(
            f"/api/rooms/{room_id}/tickets/{manual_ticket_id}/revote",
            headers=owner_headers,
        )
        assert restarted.status_code == 200
        assert restarted.json()["round"] == 2
        assert restarted.json()["votes"] == []

        auto_room = client.post(
            "/api/rooms",
            json={"name": "Concurrent auto reveal", "reveal_mode": "auto"},
            headers=owner_headers,
        ).json()
        auto_room_id = auto_room["id"]
        auto_ticket = client.post(
            f"/api/rooms/{auto_room_id}/tickets",
            json={"summary": "Concurrent ticket"},
            headers=owner_headers,
        ).json()
        auto_ticket_id = auto_ticket["id"]
        client.patch(
            f"/api/rooms/{auto_room_id}/active-ticket",
            json={"ticket_id": auto_ticket_id},
            headers=owner_headers,
        )
        client.post(
            f"/api/rooms/{auto_room_id}/join",
            json={"display_name": "Integration member"},
            headers=member_headers,
        )

        def concurrent_vote(headers: dict[str, str], value: str):
            return client.put(
                f"/api/rooms/{auto_room_id}/tickets/{auto_ticket_id}/vote",
                json={"value": value},
                headers=headers,
            )

        with ThreadPoolExecutor(max_workers=2) as executor:
            responses = list(
                executor.map(
                    lambda pair: concurrent_vote(*pair),
                    [(owner_headers, "5"), (member_headers, "8")],
                )
            )
        assert [response.status_code for response in responses] == [200, 200]
        concurrent_results = client.get(
            f"/api/rooms/{auto_room_id}/tickets/{auto_ticket_id}/votes",
            headers=owner_headers,
        )
        assert concurrent_results.json()["state"] == "revealed"
        assert len(concurrent_results.json()["votes"]) == 2

        denied = client.post(
            f"/api/rooms/{room_id}/tickets",
            json={"summary": "Member mutation"},
            headers=member_headers,
        )
        assert denied.status_code == 403

        assert client.delete(
            f"/api/rooms/{room_id}", headers=member_headers
        ).status_code == 403
        assert client.delete(
            f"/api/rooms/{room_id}", headers=owner_headers
        ).status_code == 204
        assert client.get(
            f"/api/rooms/{room_id}", headers=member_headers
        ).status_code == 404
        assert service.table("room_members").select("room_id").eq(
            "room_id", room_id
        ).execute().data == []
        assert service.table("tickets").select("room_id").eq(
            "room_id", room_id
        ).execute().data == []
        assert service.table("votes").select("room_id").eq(
            "room_id", room_id
        ).execute().data == []

    finally:
        app.dependency_overrides.clear()
        service.auth.admin.delete_user(str(owner.id))
        service.auth.admin.delete_user(str(member.id))
