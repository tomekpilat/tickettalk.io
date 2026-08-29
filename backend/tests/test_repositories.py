import json
from datetime import UTC, datetime
from types import SimpleNamespace
from uuid import UUID

from app.auth import DEVELOPMENT_USER_ID, Principal
from app.models import JiraImportRow, RevealedVote, Room, Ticket
from app.repositories import InMemoryRepository, SupabaseRepository, summarize_votes

ROOM_ID = UUID("10000000-0000-4000-8000-000000000071")


def vote(index: int, value: str) -> RevealedVote:
    return RevealedVote(
        user_id=UUID(f"00000000-0000-0000-0000-{index:012d}"),
        display_name=f"Member {index}",
        value=value,
    )


def test_seeded_development_repository_is_immediately_usable() -> None:
    repository = InMemoryRepository()
    actor = Principal(
        id=DEVELOPMENT_USER_ID,
        email="facilitator@local.tickettalks",
        display_name="Tomasz Pilat",
    )

    repository.healthcheck()
    rooms = repository.list_rooms(actor)
    tickets = repository.list_tickets(rooms[0].id, actor)

    assert rooms[0].name == "Sprint 42 · Checkout"
    assert rooms[0].ticket_count == 5
    assert len(tickets) == 5
    assert tickets[0].issue_key == "PAY-118"
    assert tickets[0].final_estimate == "5"


def test_vote_summary_covers_numeric_and_non_numeric_consensus() -> None:
    ticket = Ticket(room_id=ROOM_ID, summary="Estimate", vote_state="revealed")

    empty = summarize_votes(ROOM_ID, ticket, [])
    unanimous = summarize_votes(ROOM_ID, ticket, [vote(1, "5"), vote(2, "5")])
    close = summarize_votes(ROOM_ID, ticket, [vote(1, "5"), vote(2, "8")])
    split = summarize_votes(ROOM_ID, ticket, [vote(1, "1"), vote(2, "8")])
    tshirt = summarize_votes(ROOM_ID, ticket, [vote(1, "S"), vote(2, "M")])

    assert empty.consensus is None
    assert unanimous.consensus == "unanimous" and unanimous.average == 5
    assert close.consensus == "close" and close.minimum == 5 and close.maximum == 8
    assert split.consensus == "split"
    assert tshirt.consensus == "not_numeric" and tshirt.average is None


def test_unrevealed_summary_never_returns_vote_values() -> None:
    ticket = Ticket(room_id=ROOM_ID, summary="Estimate", vote_state="voting")
    results = summarize_votes(ROOM_ID, ticket, [vote(1, "13")])

    assert results.votes == []
    assert results.average == 13


def test_supabase_jira_import_serializes_timestamps_as_json() -> None:
    actor = Principal(
        id=DEVELOPMENT_USER_ID,
        email="facilitator@local.tickettalks",
        display_name="Facilitator",
    )
    inserted: list[dict[str, object]] = []

    class InsertQuery:
        def insert(self, values: dict[str, object]) -> "InsertQuery":
            json.dumps(values)
            inserted.append(values)
            return self

        @staticmethod
        def execute() -> SimpleNamespace:
            return SimpleNamespace(data=[])

    class Client:
        @staticmethod
        def table(name: str) -> InsertQuery:
            assert name == "tickets"
            return InsertQuery()

    class Repository(SupabaseRepository):
        def __init__(self) -> None:
            self.client = Client()

        @staticmethod
        def _require_owner_room(room_id: UUID, principal: Principal) -> Room:
            return Room(id=room_id, owner_id=principal.id, name="Jira import")

        @staticmethod
        def _next_ticket_position(_room_id: UUID) -> int:
            return 0

        @staticmethod
        def list_tickets(_room_id: UUID, _principal: Principal) -> list[Ticket]:
            return []

    imported = Repository().import_tickets(
        ROOM_ID,
        [
            JiraImportRow(
                row_number=1,
                issue_key="PAY-201",
                summary="Import Jira timestamp",
                jira_issue_id="10101",
                jira_updated_at=datetime(2026, 8, 29, 10, tzinfo=UTC),
            )
        ],
        actor,
    )

    assert imported.imported_count == 1
    assert inserted[0]["jira_updated_at"] == "2026-08-29T10:00:00Z"
