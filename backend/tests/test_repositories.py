from uuid import UUID

from app.auth import DEVELOPMENT_USER_ID, Principal
from app.models import RevealedVote, Ticket
from app.repositories import InMemoryRepository, summarize_votes

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
