from copy import deepcopy
from typing import Protocol

from supabase import Client, create_client

from .models import Room, RoomCreate, Ticket, TicketCreate


class Repository(Protocol):
    def list_rooms(self) -> list[Room]: ...
    def create_room(self, payload: RoomCreate) -> Room: ...
    def list_tickets(self, room_id: str) -> list[Ticket]: ...
    def import_tickets(self, room_id: str, payload: list[TicketCreate]) -> list[Ticket]: ...
    def update_estimate(self, ticket_id: str, points: float | None) -> Ticket | None: ...


class InMemoryRepository:
    def __init__(self) -> None:
        room = Room(id="demo-room", name="Sprint 42 · Checkout", ticket_count=5, sized_count=2, total_points=8)
        self.rooms = {room.id: room}
        seeds = [
            ("PAY-118", "Split payout ledger by currency", "Story", 5),
            ("PAY-124", "Add payment retry schedule", "Story", 3),
            ("PAY-131", "Surface failed transfer reason", "Bug", None),
            ("PAY-136", "Support partial refunds", "Story", None),
            ("PAY-142", "Export settlement report", "Task", None),
        ]
        self.tickets = {
            f"demo-{i}": Ticket(
                id=f"demo-{i}", room_id=room.id, position=i, issue_key=key,
                summary=summary, issue_type=kind, story_points=points,
                description="Acceptance criteria and implementation notes are ready for team review.",
            )
            for i, (key, summary, kind, points) in enumerate(seeds)
        }

    def list_rooms(self) -> list[Room]:
        return [deepcopy(room) for room in self.rooms.values()]

    def create_room(self, payload: RoomCreate) -> Room:
        room = Room(**payload.model_dump())
        self.rooms[room.id] = room
        return deepcopy(room)

    def list_tickets(self, room_id: str) -> list[Ticket]:
        return sorted(
            [deepcopy(ticket) for ticket in self.tickets.values() if ticket.room_id == room_id],
            key=lambda item: item.position,
        )

    def import_tickets(self, room_id: str, payload: list[TicketCreate]) -> list[Ticket]:
        created = [
            Ticket(room_id=room_id, position=index, **item.model_dump())
            for index, item in enumerate(payload)
        ]
        for ticket in created:
            self.tickets[ticket.id] = ticket
        if room_id in self.rooms:
            self.rooms[room_id].ticket_count = len(created)
        return deepcopy(created)

    def update_estimate(self, ticket_id: str, points: float | None) -> Ticket | None:
        ticket = self.tickets.get(ticket_id)
        if not ticket:
            return None
        ticket.story_points = points
        room = self.rooms[ticket.room_id]
        room_tickets = [item for item in self.tickets.values() if item.room_id == room.id]
        room.sized_count = sum(item.story_points is not None for item in room_tickets)
        room.total_points = sum(item.story_points or 0 for item in room_tickets)
        return deepcopy(ticket)


class SupabaseRepository:
    def __init__(self, url: str, key: str) -> None:
        self.client: Client = create_client(url, key)

    def list_rooms(self) -> list[Room]:
        result = self.client.table("room_rollups").select("*").order("created_at", desc=True).execute()
        return [Room.model_validate(row) for row in result.data]

    def create_room(self, payload: RoomCreate) -> Room:
        result = self.client.table("rooms").insert(payload.model_dump()).execute()
        return Room.model_validate(result.data[0])

    def list_tickets(self, room_id: str) -> list[Ticket]:
        result = self.client.table("tickets").select("*").eq("room_id", room_id).order("position").execute()
        return [Ticket.model_validate(row) for row in result.data]

    def import_tickets(self, room_id: str, payload: list[TicketCreate]) -> list[Ticket]:
        rows = [{**item.model_dump(), "room_id": room_id, "position": index} for index, item in enumerate(payload)]
        result = self.client.table("tickets").insert(rows).execute()
        return [Ticket.model_validate(row) for row in result.data]

    def update_estimate(self, ticket_id: str, points: float | None) -> Ticket | None:
        result = self.client.table("tickets").update({"story_points": points}).eq("id", ticket_id).execute()
        return Ticket.model_validate(result.data[0]) if result.data else None

