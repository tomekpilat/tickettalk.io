from datetime import UTC, datetime
from typing import Literal
from uuid import uuid4

from pydantic import BaseModel, Field

Scale = Literal["fibonacci", "extended", "tshirt"]


class TicketCreate(BaseModel):
    issue_key: str = Field(min_length=1, max_length=40)
    summary: str = Field(min_length=1, max_length=500)
    issue_type: str = "Story"
    description: str = ""
    story_points: float | None = None


class Ticket(TicketCreate):
    id: str = Field(default_factory=lambda: str(uuid4()))
    room_id: str
    position: int = 0


class RoomCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    scale: Scale = "fibonacci"
    reveal_mode: Literal["manual", "auto"] = "manual"


class Room(RoomCreate):
    id: str = Field(default_factory=lambda: str(uuid4()))
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    ticket_count: int = 0
    sized_count: int = 0
    total_points: float = 0


class TicketImport(BaseModel):
    tickets: list[TicketCreate]


class EstimateUpdate(BaseModel):
    story_points: float | None = Field(default=None, ge=0, le=1000)
