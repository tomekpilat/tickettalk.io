from copy import deepcopy
from datetime import UTC, datetime, timedelta
from typing import Protocol
from uuid import UUID

from postgrest.exceptions import APIError
from supabase import Client, create_client

from .auth import DEVELOPMENT_USER_ID, Principal
from .models import (
    JiraImportRow,
    RevealedVote,
    Room,
    RoomCreate,
    RoomJoin,
    RoomMember,
    RoomUpdate,
    Ticket,
    TicketCreate,
    TicketImportResult,
    TicketUpdate,
    Vote,
    VoteReceipt,
    VoteResults,
)

PRESENCE_WINDOW = timedelta(seconds=45)
VOTE_VALUES = {
    "fibonacci": {"0", "1", "2", "3", "5", "8", "13", "21", "?"},
    "extended": {"1", "2", "3", "5", "8", "13", "21", "34", "55", "?"},
    "tshirt": {"XS", "S", "M", "L", "XL", "?"},
}


def summarize_votes(
    room_id: UUID, ticket: Ticket, votes: list[RevealedVote]
) -> VoteResults:
    numeric_values: list[float] = []
    for vote in votes:
        try:
            numeric_values.append(float(vote.value))
        except ValueError:
            numeric_values = []
            break
    average = sum(numeric_values) / len(numeric_values) if numeric_values else None
    minimum = min(numeric_values) if numeric_values else None
    maximum = max(numeric_values) if numeric_values else None
    if not votes:
        consensus = None
    elif not numeric_values:
        consensus = "unanimous" if len({vote.value for vote in votes}) == 1 else "not_numeric"
    elif minimum == maximum:
        consensus = "unanimous"
    elif maximum - minimum <= 3:
        consensus = "close"
    else:
        consensus = "split"
    return VoteResults(
        room_id=room_id,
        ticket_id=ticket.id,
        state=ticket.vote_state,
        round=ticket.vote_round,
        votes=votes if ticket.vote_state == "revealed" else [],
        average=round(average, 1) if average is not None else None,
        minimum=minimum,
        maximum=maximum,
        consensus=consensus,
        final_estimate=ticket.final_estimate,
    )


class RepositoryError(Exception):
    """Base repository error safe to translate at the API boundary."""


class NotFoundError(RepositoryError):
    pass


class ForbiddenError(RepositoryError):
    pass


class ConflictError(RepositoryError):
    pass


class Repository(Protocol):
    def list_rooms(self, actor: Principal) -> list[Room]: ...
    def get_room(self, room_id: UUID, actor: Principal) -> Room: ...
    def create_room(self, payload: RoomCreate, actor: Principal) -> Room: ...
    def update_room(self, room_id: UUID, payload: RoomUpdate, actor: Principal) -> Room: ...
    def set_active_ticket(
        self, room_id: UUID, ticket_id: UUID | None, actor: Principal
    ) -> Room: ...
    def join_room(
        self, room_id: UUID, payload: RoomJoin, actor: Principal
    ) -> RoomMember: ...
    def list_members(self, room_id: UUID, actor: Principal) -> list[RoomMember]: ...
    def touch_presence(self, room_id: UUID, actor: Principal) -> RoomMember: ...
    def submit_vote(
        self, room_id: UUID, ticket_id: UUID, value: str, actor: Principal
    ) -> VoteReceipt: ...
    def get_vote_results(
        self, room_id: UUID, ticket_id: UUID, actor: Principal
    ) -> VoteResults: ...
    def reveal_votes(
        self, room_id: UUID, ticket_id: UUID, actor: Principal
    ) -> VoteResults: ...
    def restart_vote(
        self, room_id: UUID, ticket_id: UUID, actor: Principal
    ) -> VoteResults: ...
    def set_final_estimate(
        self, room_id: UUID, ticket_id: UUID, value: str, actor: Principal
    ) -> Ticket: ...
    def export_room(self, room_id: UUID, actor: Principal) -> tuple[Room, list[Ticket]]: ...
    def delete_room(self, room_id: UUID, actor: Principal) -> None: ...
    def list_tickets(self, room_id: UUID, actor: Principal) -> list[Ticket]: ...
    def create_ticket(
        self, room_id: UUID, payload: TicketCreate, actor: Principal
    ) -> Ticket: ...
    def update_ticket(
        self, room_id: UUID, ticket_id: UUID, payload: TicketUpdate, actor: Principal
    ) -> Ticket: ...
    def delete_ticket(self, room_id: UUID, ticket_id: UUID, actor: Principal) -> None: ...
    def reorder_tickets(
        self, room_id: UUID, ticket_ids: list[UUID], actor: Principal
    ) -> list[Ticket]: ...
    def import_tickets(
        self, room_id: UUID, rows: list[JiraImportRow], actor: Principal
    ) -> TicketImportResult: ...
    def update_estimate(
        self, ticket_id: UUID, points: float | None, actor: Principal
    ) -> Ticket | None: ...


class InMemoryRepository:
    def __init__(self, *, seed: bool = True) -> None:
        self.rooms: dict[UUID, Room] = {}
        self.tickets: dict[UUID, Ticket] = {}
        self.members: dict[UUID, dict[UUID, RoomMember]] = {}
        self.votes: dict[tuple[UUID, UUID], Vote] = {}
        if not seed:
            return
        room_id = UUID("10000000-0000-4000-8000-000000000001")
        room = Room(
            id=room_id,
            owner_id=DEVELOPMENT_USER_ID,
            name="Sprint 42 · Checkout",
            ticket_count=5,
            sized_count=2,
            total_points=8,
        )
        self.rooms[room.id] = room
        now = datetime.now(UTC)
        self.members[room.id] = {
            DEVELOPMENT_USER_ID: RoomMember(
                room_id=room.id,
                user_id=DEVELOPMENT_USER_ID,
                role="facilitator",
                display_name="Tomasz Pilat",
                joined_at=now,
                last_seen_at=now,
                is_online=True,
            )
        }
        seeds = [
            ("PAY-118", "Split payout ledger by currency", "Story", 5),
            ("PAY-124", "Add payment retry schedule", "Story", 3),
            ("PAY-131", "Surface failed transfer reason", "Bug", None),
            ("PAY-136", "Support partial refunds", "Story", None),
            ("PAY-142", "Export settlement report", "Task", None),
        ]
        for index, (key, summary, kind, points) in enumerate(seeds):
            ticket = Ticket(
                id=UUID(f"20000000-0000-0000-0000-{index + 1:012d}"),
                room_id=room.id,
                position=index,
                issue_key=key,
                summary=summary,
                issue_type=kind,
                story_points=points,
                final_estimate=str(points) if points is not None else None,
                description=(
                    "Acceptance criteria and implementation notes are ready for team review."
                ),
            )
            self.tickets[ticket.id] = ticket

    def _room(self, room_id: UUID) -> Room:
        room = self.rooms.get(room_id)
        if not room:
            raise NotFoundError("Room not found")
        return room

    def _require_member(self, room_id: UUID, actor: Principal) -> Room:
        room = self._room(room_id)
        if actor.id != room.owner_id and actor.id not in self.members.get(room_id, {}):
            raise ForbiddenError("You do not have access to this room")
        return room

    def _require_owner(self, room_id: UUID, actor: Principal) -> Room:
        room = self._room(room_id)
        if room.owner_id != actor.id:
            raise ForbiddenError("Only the facilitator can change this room")
        return room

    def list_rooms(self, actor: Principal) -> list[Room]:
        return [
            deepcopy(room)
            for room in self.rooms.values()
            if room.owner_id == actor.id
        ]

    def get_room(self, room_id: UUID, actor: Principal) -> Room:
        return deepcopy(self._require_member(room_id, actor))

    def create_room(self, payload: RoomCreate, actor: Principal) -> Room:
        room = Room(owner_id=actor.id, **payload.model_dump())
        self.rooms[room.id] = room
        now = datetime.now(UTC)
        self.members[room.id] = {
            actor.id: RoomMember(
                room_id=room.id,
                user_id=actor.id,
                role="facilitator",
                display_name=actor.display_name,
                joined_at=now,
                last_seen_at=now,
                is_online=True,
            )
        }
        return deepcopy(room)

    def update_room(self, room_id: UUID, payload: RoomUpdate, actor: Principal) -> Room:
        room = self._require_owner(room_id, actor)
        protected_settings = {"scale", "reveal_mode"} & payload.model_fields_set
        if room.ticket_count and protected_settings:
            raise ForbiddenError("Scale and reveal mode lock after tickets are added")
        for field, value in payload.model_dump(exclude_unset=True).items():
            setattr(room, field, value)
        room.updated_at = datetime.now(UTC)
        return deepcopy(room)

    def set_active_ticket(
        self, room_id: UUID, ticket_id: UUID | None, actor: Principal
    ) -> Room:
        room = self._require_owner(room_id, actor)
        if ticket_id is not None:
            ticket = self.tickets.get(ticket_id)
            if not ticket or ticket.room_id != room_id:
                raise NotFoundError("Ticket not found in this room")
        room.active_ticket_id = ticket_id
        room.updated_at = datetime.now(UTC)
        return deepcopy(room)

    def join_room(
        self, room_id: UUID, payload: RoomJoin, actor: Principal
    ) -> RoomMember:
        room = self._room(room_id)
        now = datetime.now(UTC)
        existing = self.members.setdefault(room.id, {}).get(actor.id)
        if existing:
            existing.display_name = payload.display_name
            existing.last_seen_at = now
            existing.is_online = True
            return deepcopy(existing)
        member = RoomMember(
            room_id=room.id,
            user_id=actor.id,
            role="facilitator" if room.owner_id == actor.id else "member",
            display_name=payload.display_name,
            joined_at=now,
            last_seen_at=now,
            is_online=True,
        )
        self.members[room.id][actor.id] = member
        return deepcopy(member)

    def list_members(self, room_id: UUID, actor: Principal) -> list[RoomMember]:
        room = self._require_member(room_id, actor)
        now = datetime.now(UTC)
        return [
            deepcopy(
                member.model_copy(
                    update={
                        "is_online": now - member.last_seen_at <= PRESENCE_WINDOW,
                        "has_voted": bool(
                            room.active_ticket_id
                            and (room.active_ticket_id, member.user_id) in self.votes
                        ),
                    }
                )
            )
            for member in sorted(
                self.members.get(room_id, {}).values(),
                key=lambda item: (item.role != "facilitator", item.joined_at),
            )
        ]

    def touch_presence(self, room_id: UUID, actor: Principal) -> RoomMember:
        self._require_member(room_id, actor)
        member = self.members.get(room_id, {}).get(actor.id)
        if not member:
            raise ForbiddenError("Join the room before updating presence")
        member.last_seen_at = datetime.now(UTC)
        member.is_online = True
        return deepcopy(member)

    def submit_vote(
        self, room_id: UUID, ticket_id: UUID, value: str, actor: Principal
    ) -> VoteReceipt:
        room = self._require_member(room_id, actor)
        if actor.id not in self.members.get(room_id, {}):
            raise ForbiddenError("Join the room before voting")
        if room.active_ticket_id != ticket_id:
            raise ConflictError("Votes are accepted only for the active ticket")
        if value not in VOTE_VALUES[room.scale]:
            raise ConflictError("That vote is not part of this room's scale")
        if any(
            vote.ticket_id == ticket_id and vote.revealed
            for vote in self.votes.values()
        ):
            raise ConflictError("Voting is locked after reveal")
        submitted_at = datetime.now(UTC)
        vote = Vote(
            room_id=room_id,
            ticket_id=ticket_id,
            user_id=actor.id,
            value=value,
            submitted_at=submitted_at,
        )
        self.votes[(ticket_id, actor.id)] = vote
        online_members = [
            member
            for member in self.members.get(room_id, {}).values()
            if submitted_at - member.last_seen_at <= PRESENCE_WINDOW
        ]
        if room.reveal_mode == "auto" and online_members and all(
            (ticket_id, member.user_id) in self.votes for member in online_members
        ):
            for stored_vote in self.votes.values():
                if stored_vote.ticket_id == ticket_id:
                    stored_vote.revealed = True
            ticket = self.tickets[ticket_id]
            ticket.vote_state = "revealed"
            ticket.revealed_at = submitted_at
        return VoteReceipt(
            room_id=room_id,
            ticket_id=ticket_id,
            user_id=actor.id,
            submitted_at=submitted_at,
            revealed=self.tickets[ticket_id].vote_state == "revealed",
        )

    def get_vote_results(
        self, room_id: UUID, ticket_id: UUID, actor: Principal
    ) -> VoteResults:
        self._require_member(room_id, actor)
        ticket = self.tickets.get(ticket_id)
        if not ticket or ticket.room_id != room_id:
            raise NotFoundError("Ticket not found")
        votes = []
        if ticket.vote_state == "revealed":
            for vote in self.votes.values():
                if vote.ticket_id == ticket_id:
                    member = self.members[room_id][vote.user_id]
                    votes.append(
                        RevealedVote(
                            user_id=vote.user_id,
                            display_name=member.display_name,
                            value=vote.value,
                        )
                    )
        return summarize_votes(room_id, ticket, votes)

    def reveal_votes(
        self, room_id: UUID, ticket_id: UUID, actor: Principal
    ) -> VoteResults:
        room = self._require_owner(room_id, actor)
        if room.active_ticket_id != ticket_id:
            raise ConflictError("Only the active ticket can be revealed")
        matching = [vote for vote in self.votes.values() if vote.ticket_id == ticket_id]
        if not matching:
            raise ConflictError("At least one vote is required")
        ticket = self.tickets[ticket_id]
        if ticket.vote_state != "revealed":
            for vote in matching:
                vote.revealed = True
            ticket.vote_state = "revealed"
            ticket.revealed_at = datetime.now(UTC)
        return self.get_vote_results(room_id, ticket_id, actor)

    def restart_vote(
        self, room_id: UUID, ticket_id: UUID, actor: Principal
    ) -> VoteResults:
        self._require_owner(room_id, actor)
        ticket = self.tickets.get(ticket_id)
        if not ticket or ticket.room_id != room_id:
            raise NotFoundError("Ticket not found")
        self.votes = {
            key: vote for key, vote in self.votes.items() if vote.ticket_id != ticket_id
        }
        ticket.vote_state = "voting"
        ticket.vote_round += 1
        ticket.revealed_at = None
        ticket.final_estimate = None
        return self.get_vote_results(room_id, ticket_id, actor)

    def set_final_estimate(
        self, room_id: UUID, ticket_id: UUID, value: str, actor: Principal
    ) -> Ticket:
        room = self._require_owner(room_id, actor)
        ticket = self.tickets.get(ticket_id)
        if not ticket or ticket.room_id != room_id:
            raise NotFoundError("Ticket not found")
        if ticket.vote_state != "revealed":
            raise ConflictError("Reveal votes before setting the final estimate")
        if value not in VOTE_VALUES[room.scale]:
            raise ConflictError("That estimate is not part of this room's scale")
        ticket.final_estimate = value
        self._refresh_room_stats(room)
        return deepcopy(ticket)

    def export_room(self, room_id: UUID, actor: Principal) -> tuple[Room, list[Ticket]]:
        room = self._require_owner(room_id, actor)
        return deepcopy(room), self.list_tickets(room_id, actor)

    def delete_room(self, room_id: UUID, actor: Principal) -> None:
        self._require_owner(room_id, actor)
        ticket_ids = {
            ticket.id for ticket in self.tickets.values() if ticket.room_id == room_id
        }
        self.votes = {
            key: vote for key, vote in self.votes.items() if vote.ticket_id not in ticket_ids
        }
        self.tickets = {
            ticket_id: ticket
            for ticket_id, ticket in self.tickets.items()
            if ticket.room_id != room_id
        }
        self.members.pop(room_id, None)
        del self.rooms[room_id]

    def list_tickets(self, room_id: UUID, actor: Principal) -> list[Ticket]:
        self._require_member(room_id, actor)
        return sorted(
            [deepcopy(ticket) for ticket in self.tickets.values() if ticket.room_id == room_id],
            key=lambda item: item.position,
        )

    def _assert_key_unique(
        self, room_id: UUID, issue_key: str | None, exclude_id: UUID | None = None
    ) -> None:
        if not issue_key:
            return
        if any(
            ticket.room_id == room_id
            and ticket.id != exclude_id
            and ticket.issue_key
            and ticket.issue_key.casefold() == issue_key.casefold()
            for ticket in self.tickets.values()
        ):
            raise ConflictError(f"{issue_key} already exists in this room")

    def _refresh_room_stats(self, room: Room) -> None:
        room_tickets = [item for item in self.tickets.values() if item.room_id == room.id]
        room.ticket_count = len(room_tickets)
        room.sized_count = sum(item.final_estimate is not None for item in room_tickets)
        room.total_points = sum(
            float(item.final_estimate)
            for item in room_tickets
            if item.final_estimate and item.final_estimate.replace(".", "", 1).isdigit()
        )
        room.updated_at = datetime.now(UTC)

    def create_ticket(
        self, room_id: UUID, payload: TicketCreate, actor: Principal
    ) -> Ticket:
        room = self._require_owner(room_id, actor)
        self._assert_key_unique(room_id, payload.issue_key)
        positions = [item.position for item in self.tickets.values() if item.room_id == room_id]
        ticket = Ticket(
            room_id=room_id,
            position=(max(positions) + 1 if positions else 0),
            **payload.model_dump(),
        )
        self.tickets[ticket.id] = ticket
        self._refresh_room_stats(room)
        return deepcopy(ticket)

    def update_ticket(
        self, room_id: UUID, ticket_id: UUID, payload: TicketUpdate, actor: Principal
    ) -> Ticket:
        room = self._require_owner(room_id, actor)
        ticket = self.tickets.get(ticket_id)
        if not ticket or ticket.room_id != room_id:
            raise NotFoundError("Ticket not found")
        if "issue_key" in payload.model_fields_set:
            self._assert_key_unique(room_id, payload.issue_key, ticket.id)
        for field, value in payload.model_dump(exclude_unset=True).items():
            setattr(ticket, field, value)
        self._refresh_room_stats(room)
        return deepcopy(ticket)

    def delete_ticket(self, room_id: UUID, ticket_id: UUID, actor: Principal) -> None:
        room = self._require_owner(room_id, actor)
        ticket = self.tickets.get(ticket_id)
        if not ticket or ticket.room_id != room_id:
            raise NotFoundError("Ticket not found")
        ordered_before = sorted(
            [item for item in self.tickets.values() if item.room_id == room_id],
            key=lambda item: item.position,
        )
        deleted_index = next(
            index for index, item in enumerate(ordered_before) if item.id == ticket_id
        )
        del self.tickets[ticket_id]
        remaining = sorted(
            [item for item in self.tickets.values() if item.room_id == room_id],
            key=lambda item: item.position,
        )
        for position, item in enumerate(remaining):
            item.position = position
        if room.active_ticket_id == ticket_id:
            replacement_index = min(deleted_index, len(remaining) - 1)
            room.active_ticket_id = (
                remaining[replacement_index].id if remaining else None
            )
        self._refresh_room_stats(room)

    def reorder_tickets(
        self, room_id: UUID, ticket_ids: list[UUID], actor: Principal
    ) -> list[Ticket]:
        self._require_owner(room_id, actor)
        current = [item for item in self.tickets.values() if item.room_id == room_id]
        if set(ticket_ids) != {item.id for item in current}:
            raise ConflictError("Ticket order must include every room ticket exactly once")
        for position, ticket_id in enumerate(ticket_ids):
            self.tickets[ticket_id].position = position
        return self.list_tickets(room_id, actor)

    def import_tickets(
        self, room_id: UUID, rows: list[JiraImportRow], actor: Principal
    ) -> TicketImportResult:
        room = self._require_owner(room_id, actor)
        imported_count = 0
        replaced_count = 0
        skipped_count = 0
        for row in rows:
            if row.action == "skip":
                skipped_count += 1
                continue
            values = row.model_dump(
                exclude={"row_number", "action", "existing_ticket_id"}
            )
            if row.action == "replace" and row.existing_ticket_id:
                ticket = self.tickets.get(row.existing_ticket_id)
                if not ticket or ticket.room_id != room_id:
                    raise ConflictError("The backlog changed after preview; preview the import again")
                for field, value in values.items():
                    setattr(ticket, field, value)
                replaced_count += 1
                continue
            self._assert_key_unique(room_id, row.issue_key)
            positions = [
                item.position for item in self.tickets.values() if item.room_id == room_id
            ]
            ticket = Ticket(
                room_id=room_id,
                position=(max(positions) + 1 if positions else 0),
                **values,
            )
            self.tickets[ticket.id] = ticket
            imported_count += 1
        self._refresh_room_stats(room)
        return TicketImportResult(
            tickets=self.list_tickets(room_id, actor),
            imported_count=imported_count,
            replaced_count=replaced_count,
            skipped_count=skipped_count,
        )

    def update_estimate(
        self, ticket_id: UUID, points: float | None, actor: Principal
    ) -> Ticket | None:
        ticket = self.tickets.get(ticket_id)
        if not ticket:
            return None
        room = self._require_owner(ticket.room_id, actor)
        ticket.story_points = points
        self._refresh_room_stats(room)
        return deepcopy(ticket)


class SupabaseRepository:
    def __init__(self, url: str, key: str) -> None:
        self.client: Client = create_client(url, key)

    @staticmethod
    def _first(data: list[dict] | dict | None) -> dict | None:
        if isinstance(data, list):
            return data[0] if data else None
        return data

    def _membership(self, room_id: UUID, actor: Principal) -> str | None:
        result = (
            self.client.table("room_members")
            .select("role")
            .eq("room_id", str(room_id))
            .eq("user_id", str(actor.id))
            .limit(1)
            .execute()
        )
        row = self._first(result.data)
        return str(row["role"]) if row else None

    def list_rooms(self, actor: Principal) -> list[Room]:
        result = (
            self.client.table("room_rollups")
            .select("*")
            .eq("owner_id", str(actor.id))
            .order("created_at", desc=True)
            .execute()
        )
        return [Room.model_validate(row) for row in result.data]

    def get_room(self, room_id: UUID, actor: Principal) -> Room:
        result = (
            self.client.table("room_rollups")
            .select("*")
            .eq("id", str(room_id))
            .limit(1)
            .execute()
        )
        row = self._first(result.data)
        if not row:
            raise NotFoundError("Room not found")
        if str(row["owner_id"]) != str(actor.id) and not self._membership(room_id, actor):
            raise ForbiddenError("You do not have access to this room")
        return Room.model_validate(row)

    def create_room(self, payload: RoomCreate, actor: Principal) -> Room:
        result = self.client.rpc(
            "create_room_with_facilitator",
            {
                "p_owner_id": str(actor.id),
                "p_display_name": actor.display_name,
                "p_name": payload.name,
                "p_scale": payload.scale,
                "p_reveal_mode": payload.reveal_mode,
            },
        ).execute()
        row = self._first(result.data)
        if not row:
            raise RepositoryError("Room creation returned no data")
        return Room.model_validate(row)

    def update_room(self, room_id: UUID, payload: RoomUpdate, actor: Principal) -> Room:
        room = self.get_room(room_id, actor)
        if room.owner_id != actor.id:
            raise ForbiddenError("Only the facilitator can change this room")
        protected_settings = {"scale", "reveal_mode"} & payload.model_fields_set
        if room.ticket_count and protected_settings:
            raise ForbiddenError("Scale and reveal mode lock after tickets are added")
        result = (
            self.client.table("rooms")
            .update(payload.model_dump(exclude_unset=True))
            .eq("id", str(room_id))
            .eq("owner_id", str(actor.id))
            .execute()
        )
        if not self._first(result.data):
            raise ForbiddenError("Only the facilitator can change this room")
        return self.get_room(room_id, actor)

    def set_active_ticket(
        self, room_id: UUID, ticket_id: UUID | None, actor: Principal
    ) -> Room:
        self._require_owner_room(room_id, actor)
        if ticket_id is not None:
            ticket_result = (
                self.client.table("tickets")
                .select("id")
                .eq("room_id", str(room_id))
                .eq("id", str(ticket_id))
                .limit(1)
                .execute()
            )
            if not self._first(ticket_result.data):
                raise NotFoundError("Ticket not found in this room")
        result = (
            self.client.table("rooms")
            .update({"active_ticket_id": str(ticket_id) if ticket_id else None})
            .eq("id", str(room_id))
            .eq("owner_id", str(actor.id))
            .execute()
        )
        if not self._first(result.data):
            raise ForbiddenError("Only the facilitator can change the active ticket")
        return self.get_room(room_id, actor)

    @staticmethod
    def _member_from_row(row: dict, voted_user_ids: set[str] | None = None) -> RoomMember:
        member = RoomMember.model_validate(row)
        now = datetime.now(UTC)
        return member.model_copy(
            update={
                "is_online": now - member.last_seen_at <= PRESENCE_WINDOW,
                "has_voted": str(member.user_id) in (voted_user_ids or set()),
            }
        )

    def join_room(
        self, room_id: UUID, payload: RoomJoin, actor: Principal
    ) -> RoomMember:
        room_result = (
            self.client.table("rooms")
            .select("id,owner_id")
            .eq("id", str(room_id))
            .limit(1)
            .execute()
        )
        room = self._first(room_result.data)
        if not room:
            raise NotFoundError("Room unavailable")

        now = datetime.now(UTC).isoformat()
        self.client.table("profiles").upsert(
            {"id": str(actor.id), "display_name": payload.display_name},
            on_conflict="id",
        ).execute()
        existing_result = (
            self.client.table("room_members")
            .select("*")
            .eq("room_id", str(room_id))
            .eq("user_id", str(actor.id))
            .limit(1)
            .execute()
        )
        existing = self._first(existing_result.data)
        if existing:
            result = (
                self.client.table("room_members")
                .update({"display_name": payload.display_name, "last_seen_at": now})
                .eq("room_id", str(room_id))
                .eq("user_id", str(actor.id))
                .execute()
            )
        else:
            result = self.client.table("room_members").insert(
                {
                    "room_id": str(room_id),
                    "user_id": str(actor.id),
                    "role": (
                        "facilitator"
                        if str(room["owner_id"]) == str(actor.id)
                        else "member"
                    ),
                    "display_name": payload.display_name,
                    "last_seen_at": now,
                }
            ).execute()
        row = self._first(result.data)
        if not row:
            raise RepositoryError("Room membership returned no data")
        return self._member_from_row(row)

    def list_members(self, room_id: UUID, actor: Principal) -> list[RoomMember]:
        room = self.get_room(room_id, actor)
        result = (
            self.client.table("room_members")
            .select("*")
            .eq("room_id", str(room_id))
            .order("joined_at")
            .execute()
        )
        voted_user_ids: set[str] = set()
        if room.active_ticket_id:
            votes = (
                self.client.table("votes")
                .select("user_id")
                .eq("room_id", str(room_id))
                .eq("ticket_id", str(room.active_ticket_id))
                .execute()
            )
            voted_user_ids = {str(row["user_id"]) for row in votes.data}
        members = [
            self._member_from_row(row, voted_user_ids) for row in result.data
        ]
        return sorted(
            members, key=lambda item: (item.role != "facilitator", item.joined_at)
        )

    def touch_presence(self, room_id: UUID, actor: Principal) -> RoomMember:
        self.get_room(room_id, actor)
        result = (
            self.client.table("room_members")
            .update({"last_seen_at": datetime.now(UTC).isoformat()})
            .eq("room_id", str(room_id))
            .eq("user_id", str(actor.id))
            .execute()
        )
        row = self._first(result.data)
        if not row:
            raise ForbiddenError("Join the room before updating presence")
        return self._member_from_row(row)

    def submit_vote(
        self, room_id: UUID, ticket_id: UUID, value: str, actor: Principal
    ) -> VoteReceipt:
        room = self.get_room(room_id, actor)
        if not self._membership(room_id, actor):
            raise ForbiddenError("Join the room before voting")
        if room.active_ticket_id != ticket_id:
            raise ConflictError("Votes are accepted only for the active ticket")
        if value not in VOTE_VALUES[room.scale]:
            raise ConflictError("That vote is not part of this room's scale")
        revealed = (
            self.client.table("votes")
            .select("ticket_id")
            .eq("room_id", str(room_id))
            .eq("ticket_id", str(ticket_id))
            .eq("revealed", True)
            .limit(1)
            .execute()
        )
        if self._first(revealed.data):
            raise ConflictError("Voting is locked after reveal")
        submitted_at = datetime.now(UTC)
        self.client.table("votes").upsert(
            {
                "room_id": str(room_id),
                "ticket_id": str(ticket_id),
                "user_id": str(actor.id),
                "value": value,
                "revealed": False,
                "updated_at": submitted_at.isoformat(),
            },
            on_conflict="ticket_id,user_id",
        ).execute()
        ticket = self._ticket_in_room(room_id, ticket_id)
        return VoteReceipt(
            room_id=room_id,
            ticket_id=ticket_id,
            user_id=actor.id,
            submitted_at=submitted_at,
            revealed=ticket.vote_state == "revealed",
        )

    def _ticket_in_room(self, room_id: UUID, ticket_id: UUID) -> Ticket:
        result = (
            self.client.table("tickets")
            .select("*")
            .eq("room_id", str(room_id))
            .eq("id", str(ticket_id))
            .limit(1)
            .execute()
        )
        row = self._first(result.data)
        if not row:
            raise NotFoundError("Ticket not found")
        return Ticket.model_validate(row)

    def get_vote_results(
        self, room_id: UUID, ticket_id: UUID, actor: Principal
    ) -> VoteResults:
        self.get_room(room_id, actor)
        ticket = self._ticket_in_room(room_id, ticket_id)
        votes: list[RevealedVote] = []
        if ticket.vote_state == "revealed":
            vote_rows = (
                self.client.table("votes")
                .select("user_id,value")
                .eq("room_id", str(room_id))
                .eq("ticket_id", str(ticket_id))
                .eq("revealed", True)
                .execute()
            )
            members = (
                self.client.table("room_members")
                .select("user_id,display_name")
                .eq("room_id", str(room_id))
                .execute()
            )
            names = {str(row["user_id"]): row["display_name"] for row in members.data}
            votes = [
                RevealedVote(
                    user_id=row["user_id"],
                    display_name=names.get(str(row["user_id"]), "Participant"),
                    value=row["value"],
                )
                for row in vote_rows.data
            ]
        return summarize_votes(room_id, ticket, votes)

    def reveal_votes(
        self, room_id: UUID, ticket_id: UUID, actor: Principal
    ) -> VoteResults:
        self._require_owner_room(room_id, actor)
        try:
            self.client.rpc(
                "reveal_ticket_votes",
                {
                    "p_room_id": str(room_id),
                    "p_ticket_id": str(ticket_id),
                    "p_actor_id": str(actor.id),
                },
            ).execute()
        except APIError as error:
            if error.code in {"22023", "P0002"}:
                raise ConflictError(error.message) from error
            raise
        return self.get_vote_results(room_id, ticket_id, actor)

    def restart_vote(
        self, room_id: UUID, ticket_id: UUID, actor: Principal
    ) -> VoteResults:
        self._require_owner_room(room_id, actor)
        self.client.rpc(
            "restart_ticket_vote",
            {
                "p_room_id": str(room_id),
                "p_ticket_id": str(ticket_id),
                "p_actor_id": str(actor.id),
            },
        ).execute()
        return self.get_vote_results(room_id, ticket_id, actor)

    def set_final_estimate(
        self, room_id: UUID, ticket_id: UUID, value: str, actor: Principal
    ) -> Ticket:
        room = self._require_owner_room(room_id, actor)
        ticket = self._ticket_in_room(room_id, ticket_id)
        if ticket.vote_state != "revealed":
            raise ConflictError("Reveal votes before setting the final estimate")
        if value not in VOTE_VALUES[room.scale]:
            raise ConflictError("That estimate is not part of this room's scale")
        result = (
            self.client.table("tickets")
            .update({"final_estimate": value})
            .eq("room_id", str(room_id))
            .eq("id", str(ticket_id))
            .execute()
        )
        row = self._first(result.data)
        if not row:
            raise NotFoundError("Ticket not found")
        return Ticket.model_validate(row)

    def export_room(self, room_id: UUID, actor: Principal) -> tuple[Room, list[Ticket]]:
        room = self._require_owner_room(room_id, actor)
        return room, self.list_tickets(room_id, actor)

    def delete_room(self, room_id: UUID, actor: Principal) -> None:
        self._require_owner_room(room_id, actor)
        result = (
            self.client.table("rooms")
            .delete()
            .eq("id", str(room_id))
            .eq("owner_id", str(actor.id))
            .execute()
        )
        if not self._first(result.data):
            raise NotFoundError("Room not found")

    def list_tickets(self, room_id: UUID, actor: Principal) -> list[Ticket]:
        self.get_room(room_id, actor)
        result = (
            self.client.table("tickets")
            .select("*")
            .eq("room_id", str(room_id))
            .order("position")
            .execute()
        )
        return [Ticket.model_validate(row) for row in result.data]

    def _require_owner_room(self, room_id: UUID, actor: Principal) -> Room:
        room = self.get_room(room_id, actor)
        if room.owner_id != actor.id:
            raise ForbiddenError("Only the facilitator can change the backlog")
        return room

    @staticmethod
    def _raise_ticket_conflict(error: APIError) -> None:
        if error.code == "23505":
            raise ConflictError("That issue key already exists in this room") from error
        raise error

    def _next_ticket_position(self, room_id: UUID) -> int:
        result = (
            self.client.table("tickets")
            .select("position")
            .eq("room_id", str(room_id))
            .order("position", desc=True)
            .limit(1)
            .execute()
        )
        row = self._first(result.data)
        return int(row["position"]) + 1 if row else 0

    def create_ticket(
        self, room_id: UUID, payload: TicketCreate, actor: Principal
    ) -> Ticket:
        self._require_owner_room(room_id, actor)
        try:
            result = self.client.table("tickets").insert(
                {
                    **payload.model_dump(),
                    "room_id": str(room_id),
                    "position": self._next_ticket_position(room_id),
                }
            ).execute()
        except APIError as error:
            self._raise_ticket_conflict(error)
        row = self._first(result.data)
        if not row:
            raise RepositoryError("Ticket creation returned no data")
        return Ticket.model_validate(row)

    def update_ticket(
        self, room_id: UUID, ticket_id: UUID, payload: TicketUpdate, actor: Principal
    ) -> Ticket:
        self._require_owner_room(room_id, actor)
        try:
            result = (
                self.client.table("tickets")
                .update(payload.model_dump(exclude_unset=True))
                .eq("room_id", str(room_id))
                .eq("id", str(ticket_id))
                .execute()
            )
        except APIError as error:
            self._raise_ticket_conflict(error)
        row = self._first(result.data)
        if not row:
            raise NotFoundError("Ticket not found")
        return Ticket.model_validate(row)

    def delete_ticket(self, room_id: UUID, ticket_id: UUID, actor: Principal) -> None:
        room = self._require_owner_room(room_id, actor)
        ordered_before = (
            self.client.table("tickets")
            .select("id,position")
            .eq("room_id", str(room_id))
            .order("position")
            .execute()
        )
        deleted_index = next(
            (
                index
                for index, row in enumerate(ordered_before.data)
                if str(row["id"]) == str(ticket_id)
            ),
            None,
        )
        if deleted_index is None:
            raise NotFoundError("Ticket not found")
        result = (
            self.client.table("tickets")
            .delete()
            .eq("room_id", str(room_id))
            .eq("id", str(ticket_id))
            .execute()
        )
        if not self._first(result.data):
            raise NotFoundError("Ticket not found")
        remaining = (
            self.client.table("tickets")
            .select("id")
            .eq("room_id", str(room_id))
            .order("position")
            .execute()
        )
        if remaining.data:
            self.client.rpc(
                "reorder_room_tickets",
                {
                    "p_room_id": str(room_id),
                    "p_ticket_ids": [str(row["id"]) for row in remaining.data],
                },
            ).execute()
        if room.active_ticket_id == ticket_id:
            replacement_index = min(deleted_index, len(remaining.data) - 1)
            replacement_id = (
                str(remaining.data[replacement_index]["id"])
                if remaining.data
                else None
            )
            self.client.table("rooms").update(
                {"active_ticket_id": replacement_id}
            ).eq("id", str(room_id)).execute()

    def reorder_tickets(
        self, room_id: UUID, ticket_ids: list[UUID], actor: Principal
    ) -> list[Ticket]:
        self._require_owner_room(room_id, actor)
        try:
            result = self.client.rpc(
                "reorder_room_tickets",
                {
                    "p_room_id": str(room_id),
                    "p_ticket_ids": [str(ticket_id) for ticket_id in ticket_ids],
                },
            ).execute()
        except APIError as error:
            if error.code in {"22023", "23505"}:
                raise ConflictError(
                    "Ticket order must include every room ticket exactly once"
                ) from error
            raise
        return [Ticket.model_validate(row) for row in result.data]

    def import_tickets(
        self, room_id: UUID, rows: list[JiraImportRow], actor: Principal
    ) -> TicketImportResult:
        self._require_owner_room(room_id, actor)
        imported_count = 0
        replaced_count = 0
        skipped_count = 0
        next_position = self._next_ticket_position(room_id)
        try:
            for row in rows:
                if row.action == "skip":
                    skipped_count += 1
                    continue
                values = row.model_dump(
                    exclude={"row_number", "action", "existing_ticket_id"}
                )
                if row.action == "replace" and row.existing_ticket_id:
                    updated = (
                        self.client.table("tickets")
                        .update(values)
                        .eq("room_id", str(room_id))
                        .eq("id", str(row.existing_ticket_id))
                        .execute()
                    )
                    if not self._first(updated.data):
                        raise ConflictError(
                            "The backlog changed after preview; preview the import again"
                        )
                    replaced_count += 1
                    continue
                self.client.table("tickets").insert(
                    {
                        **values,
                        "room_id": str(room_id),
                        "position": next_position,
                    }
                ).execute()
                next_position += 1
                imported_count += 1
        except APIError as error:
            self._raise_ticket_conflict(error)
        return TicketImportResult(
            tickets=self.list_tickets(room_id, actor),
            imported_count=imported_count,
            replaced_count=replaced_count,
            skipped_count=skipped_count,
        )

    def update_estimate(
        self, ticket_id: UUID, points: float | None, actor: Principal
    ) -> Ticket | None:
        found = (
            self.client.table("tickets")
            .select("room_id")
            .eq("id", str(ticket_id))
            .limit(1)
            .execute()
        )
        ticket_row = self._first(found.data)
        if not ticket_row:
            return None
        room = self.get_room(UUID(str(ticket_row["room_id"])), actor)
        if room.owner_id != actor.id:
            raise ForbiddenError("Only the facilitator can set the final estimate")
        result = (
            self.client.table("tickets")
            .update({"story_points": points})
            .eq("id", str(ticket_id))
            .execute()
        )
        row = self._first(result.data)
        return Ticket.model_validate(row) if row else None
