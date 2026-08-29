from uuid import UUID

import pytest
from pydantic import ValidationError

from app.models import (
    FinalEstimateUpdate,
    RoomCreate,
    RoomJoin,
    RoomUpdate,
    TicketCreate,
    TicketOrder,
    TicketUpdate,
    VoteSubmission,
)

ID_A = UUID("00000000-0000-0000-0000-000000000001")
ID_B = UUID("00000000-0000-0000-0000-000000000002")


def test_ticket_models_normalize_user_input() -> None:
    created = TicketCreate(
        issue_key=" pay-1 ",
        summary="  Retry   checkout ",
        issue_type=" User   story ",
    )
    updated = TicketUpdate(issue_key=" ", summary=" Updated   title ")

    assert created.issue_key == "PAY-1"
    assert created.summary == "Retry checkout"
    assert created.issue_type == "User story"
    assert updated.issue_key is None
    assert updated.summary == "Updated title"


@pytest.mark.parametrize(
    "factory",
    [
        lambda: TicketCreate(summary=" "),
        lambda: TicketUpdate(),
        lambda: TicketUpdate(summary=None),
        lambda: TicketUpdate(issue_type=" "),
    ],
)
def test_ticket_models_reject_empty_changes(factory) -> None:
    with pytest.raises(ValidationError):
        factory()


def test_ticket_order_requires_unique_ids() -> None:
    assert TicketOrder(ticket_ids=[ID_A, ID_B]).ticket_ids == [ID_A, ID_B]
    with pytest.raises(ValidationError, match="duplicate"):
        TicketOrder(ticket_ids=[ID_A, ID_A])


def test_room_models_normalize_and_validate_names() -> None:
    room = RoomCreate(name="  Sprint   planning ", display_name="  Maya   Chen ")
    assert room.name == "Sprint planning"
    assert room.display_name == "Maya Chen"
    assert RoomUpdate(name="  Next   sprint ").name == "Next sprint"
    assert RoomJoin(display_name="  Maya   Chen ").display_name == "Maya Chen"

    for factory in (
        lambda: RoomCreate(name=" x "),
        lambda: RoomCreate(name="Valid room", display_name=" "),
        lambda: RoomUpdate(),
        lambda: RoomUpdate(name=" "),
        lambda: RoomJoin(display_name=" "),
    ):
        with pytest.raises(ValidationError):
            factory()


def test_vote_and_final_estimate_values_are_normalized_and_nonempty() -> None:
    assert VoteSubmission(value=" xs ").value == "XS"
    assert FinalEstimateUpdate(value=" 8 ").value == "8"

    with pytest.raises(ValidationError, match="Choose a vote"):
        VoteSubmission(value=" ")
    with pytest.raises(ValidationError, match="Choose a final estimate"):
        FinalEstimateUpdate(value=" ")
