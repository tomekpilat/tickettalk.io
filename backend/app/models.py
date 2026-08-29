from datetime import UTC, datetime
from typing import Literal
from uuid import UUID, uuid4

from pydantic import BaseModel, Field, field_validator, model_validator

Scale = Literal["fibonacci", "extended", "tshirt"]
RevealMode = Literal["manual", "auto"]


class TicketCreate(BaseModel):
    issue_key: str = Field(min_length=1, max_length=40)
    summary: str = Field(min_length=1, max_length=500)
    issue_type: str = "Story"
    description: str = ""
    story_points: float | None = None


class Ticket(TicketCreate):
    id: UUID = Field(default_factory=uuid4)
    room_id: UUID
    position: int = 0


class RoomCreate(BaseModel):
    name: str = Field(min_length=3, max_length=120)
    scale: Scale = "fibonacci"
    reveal_mode: RevealMode = "manual"

    @field_validator("name")
    @classmethod
    def normalize_name(cls, value: str) -> str:
        normalized = " ".join(value.split())
        if len(normalized) < 3:
            raise ValueError("Room name needs at least 3 characters")
        return normalized


class RoomUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=3, max_length=120)
    scale: Scale | None = None
    reveal_mode: RevealMode | None = None

    @field_validator("name")
    @classmethod
    def normalize_name(cls, value: str | None) -> str | None:
        if value is None:
            return value
        normalized = " ".join(value.split())
        if len(normalized) < 3:
            raise ValueError("Room name needs at least 3 characters")
        return normalized

    @model_validator(mode="after")
    def require_change(self) -> "RoomUpdate":
        if not self.model_fields_set:
            raise ValueError("Provide at least one room setting")
        return self


class Room(RoomCreate):
    id: UUID = Field(default_factory=uuid4)
    owner_id: UUID
    active_ticket_id: UUID | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    ticket_count: int = 0
    sized_count: int = 0
    total_points: float = 0


class RoomJoin(BaseModel):
    display_name: str = Field(min_length=1, max_length=80)

    @field_validator("display_name")
    @classmethod
    def normalize_display_name(cls, value: str) -> str:
        normalized = " ".join(value.split())
        if not normalized:
            raise ValueError("Enter your name to join")
        return normalized


class RoomMember(BaseModel):
    room_id: UUID
    user_id: UUID
    role: Literal["facilitator", "member"]
    display_name: str
    joined_at: datetime
    last_seen_at: datetime
    is_online: bool = False
    has_voted: bool = False


class TicketImport(BaseModel):
    tickets: list[TicketCreate]


class EstimateUpdate(BaseModel):
    story_points: float | None = Field(default=None, ge=0, le=1000)
