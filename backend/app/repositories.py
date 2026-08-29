from copy import deepcopy
from datetime import UTC, datetime
from typing import Protocol
from uuid import UUID

from supabase import Client, create_client

from .auth import DEVELOPMENT_USER_ID, Principal
from .models import Room, RoomCreate, RoomUpdate, Ticket, TicketCreate


class RepositoryError(Exception):
    """Base repository error safe to translate at the API boundary."""


class NotFoundError(RepositoryError):
    pass


class ForbiddenError(RepositoryError):
    pass


class Repository(Protocol):
    def list_rooms(self, actor: Principal) -> list[Room]: ...
    def get_room(self, room_id: UUID, actor: Principal) -> Room: ...
    def create_room(self, payload: RoomCreate, actor: Principal) -> Room: ...
    def update_room(self, room_id: UUID, payload: RoomUpdate, actor: Principal) -> Room: ...
    def list_tickets(self, room_id: UUID, actor: Principal) -> list[Ticket]: ...
    def import_tickets(
        self, room_id: UUID, payload: list[TicketCreate], actor: Principal
    ) -> list[Ticket]: ...
    def update_estimate(
        self, ticket_id: UUID, points: float | None, actor: Principal
    ) -> Ticket | None: ...


class InMemoryRepository:
    def __init__(self, *, seed: bool = True) -> None:
        self.rooms: dict[UUID, Room] = {}
        self.tickets: dict[UUID, Ticket] = {}
        self.members: dict[UUID, dict[UUID, str]] = {}
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
        self.members[room.id] = {DEVELOPMENT_USER_ID: "facilitator"}
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
        self.members[room.id] = {actor.id: "facilitator"}
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

    def list_tickets(self, room_id: UUID, actor: Principal) -> list[Ticket]:
        self._require_member(room_id, actor)
        return sorted(
            [deepcopy(ticket) for ticket in self.tickets.values() if ticket.room_id == room_id],
            key=lambda item: item.position,
        )

    def import_tickets(
        self, room_id: UUID, payload: list[TicketCreate], actor: Principal
    ) -> list[Ticket]:
        room = self._require_owner(room_id, actor)
        existing_count = len(
            [ticket for ticket in self.tickets.values() if ticket.room_id == room_id]
        )
        created = [
            Ticket(room_id=room_id, position=existing_count + index, **item.model_dump())
            for index, item in enumerate(payload)
        ]
        for ticket in created:
            self.tickets[ticket.id] = ticket
        room.ticket_count = existing_count + len(created)
        room.updated_at = datetime.now(UTC)
        return deepcopy(created)

    def update_estimate(
        self, ticket_id: UUID, points: float | None, actor: Principal
    ) -> Ticket | None:
        ticket = self.tickets.get(ticket_id)
        if not ticket:
            return None
        room = self._require_owner(ticket.room_id, actor)
        ticket.story_points = points
        room_tickets = [item for item in self.tickets.values() if item.room_id == room.id]
        room.sized_count = sum(item.story_points is not None for item in room_tickets)
        room.total_points = sum(item.story_points or 0 for item in room_tickets)
        room.updated_at = datetime.now(UTC)
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

    def import_tickets(
        self, room_id: UUID, payload: list[TicketCreate], actor: Principal
    ) -> list[Ticket]:
        room = self.get_room(room_id, actor)
        if room.owner_id != actor.id:
            raise ForbiddenError("Only the facilitator can change the backlog")
        last_position = (
            self.client.table("tickets")
            .select("position")
            .eq("room_id", str(room_id))
            .order("position", desc=True)
            .limit(1)
            .execute()
        )
        last_row = self._first(last_position.data)
        start_position = int(last_row["position"]) + 1 if last_row else 0
        rows = [
            {
                **item.model_dump(),
                "room_id": str(room_id),
                "position": start_position + index,
            }
            for index, item in enumerate(payload)
        ]
        result = self.client.table("tickets").insert(rows).execute()
        return [Ticket.model_validate(row) for row in result.data]

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
