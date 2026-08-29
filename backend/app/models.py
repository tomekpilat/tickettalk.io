from datetime import UTC, datetime
from typing import Literal
from uuid import UUID, uuid4

from pydantic import BaseModel, Field, field_validator, model_validator

Scale = Literal["fibonacci", "extended", "tshirt"]
RevealMode = Literal["manual", "auto"]


class TicketCreate(BaseModel):
    issue_key: str | None = Field(default=None, min_length=1, max_length=40)
    summary: str = Field(min_length=1, max_length=500)
    issue_type: str = Field(default="Story", min_length=1, max_length=80)
    description: str = Field(default="", max_length=20_000)
    story_points: float | None = None

    @field_validator("issue_key")
    @classmethod
    def normalize_issue_key(cls, value: str | None) -> str | None:
        normalized = value.strip().upper() if value else None
        return normalized or None

    @field_validator("summary", "issue_type")
    @classmethod
    def normalize_required_text(cls, value: str) -> str:
        normalized = " ".join(value.split())
        if not normalized:
            raise ValueError("Value cannot be empty")
        return normalized


class Ticket(TicketCreate):
    id: UUID = Field(default_factory=uuid4)
    room_id: UUID
    position: int = 0
    final_estimate: str | None = None
    vote_state: Literal["voting", "revealed"] = "voting"
    vote_round: int = 1
    revealed_at: datetime | None = None
    jira_site_url: str | None = None
    jira_issue_id: str | None = None
    jira_updated_at: datetime | None = None
    jira_assignee_account_id: str | None = None
    jira_assignee_display_name: str | None = None
    final_assignee_account_id: str | None = None
    final_assignee_display_name: str | None = None
    jira_writeback_at: datetime | None = None
    jira_writeback_error: str | None = None


class TicketUpdate(BaseModel):
    issue_key: str | None = Field(default=None, max_length=40)
    summary: str | None = Field(default=None, min_length=1, max_length=500)
    issue_type: str | None = Field(default=None, min_length=1, max_length=80)
    description: str | None = Field(default=None, max_length=20_000)

    @field_validator("issue_key")
    @classmethod
    def normalize_issue_key(cls, value: str | None) -> str | None:
        normalized = value.strip().upper() if value else None
        return normalized or None

    @field_validator("summary", "issue_type")
    @classmethod
    def normalize_optional_text(cls, value: str | None) -> str | None:
        if value is None:
            return value
        normalized = " ".join(value.split())
        if not normalized:
            raise ValueError("Value cannot be empty")
        return normalized

    @model_validator(mode="after")
    def require_change(self) -> "TicketUpdate":
        if not self.model_fields_set:
            raise ValueError("Provide at least one ticket field")
        if "summary" in self.model_fields_set and self.summary is None:
            raise ValueError("Summary cannot be empty")
        return self


class TicketOrder(BaseModel):
    ticket_ids: list[UUID] = Field(min_length=1, max_length=500)

    @model_validator(mode="after")
    def require_unique_ids(self) -> "TicketOrder":
        if len(set(self.ticket_ids)) != len(self.ticket_ids):
            raise ValueError("Ticket order cannot contain duplicate IDs")
        return self


class RoomCreate(BaseModel):
    name: str = Field(min_length=3, max_length=120)
    scale: Scale = "fibonacci"
    reveal_mode: RevealMode = "manual"
    display_name: str | None = Field(default=None, min_length=1, max_length=80)

    @field_validator("name")
    @classmethod
    def normalize_name(cls, value: str) -> str:
        normalized = " ".join(value.split())
        if len(normalized) < 3:
            raise ValueError("Room name needs at least 3 characters")
        return normalized

    @field_validator("display_name")
    @classmethod
    def normalize_display_name(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = " ".join(value.split())
        if not normalized:
            raise ValueError("Enter your name to create a room")
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


class Room(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    owner_id: UUID
    name: str
    scale: Scale = "fibonacci"
    reveal_mode: RevealMode = "manual"
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


class ActiveTicketUpdate(BaseModel):
    ticket_id: UUID | None


class VoteSubmission(BaseModel):
    value: str = Field(min_length=1, max_length=8)

    @field_validator("value")
    @classmethod
    def normalize_value(cls, value: str) -> str:
        normalized = value.strip().upper()
        if not normalized:
            raise ValueError("Choose a vote")
        return normalized


class VoteReceipt(BaseModel):
    room_id: UUID
    ticket_id: UUID
    user_id: UUID
    has_voted: bool = True
    revealed: bool = False
    submitted_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class Vote(VoteReceipt):
    value: str
    revealed: bool = False


class RevealedVote(BaseModel):
    user_id: UUID
    display_name: str
    value: str


class VoteResults(BaseModel):
    room_id: UUID
    ticket_id: UUID
    state: Literal["voting", "revealed"]
    round: int = 1
    votes: list[RevealedVote] = Field(default_factory=list)
    average: float | None = None
    minimum: float | None = None
    maximum: float | None = None
    consensus: Literal["unanimous", "close", "split", "not_numeric"] | None = None
    final_estimate: str | None = None


class FinalEstimateUpdate(BaseModel):
    value: str = Field(min_length=1, max_length=8)

    @field_validator("value")
    @classmethod
    def normalize_value(cls, value: str) -> str:
        normalized = value.strip().upper()
        if not normalized:
            raise ValueError("Choose a final estimate")
        return normalized


DuplicateBehavior = Literal["error", "skip", "replace"]
ImportAction = Literal["import", "skip", "replace"]


class JiraImportRequest(BaseModel):
    content: str = Field(min_length=1, max_length=1_000_000)
    duplicate_behavior: DuplicateBehavior = "error"


class JiraImportRow(TicketCreate):
    row_number: int
    action: ImportAction = "import"
    existing_ticket_id: UUID | None = None
    jira_site_url: str | None = Field(default=None, max_length=500)
    jira_issue_id: str | None = Field(default=None, max_length=80)
    jira_updated_at: datetime | None = None
    jira_assignee_account_id: str | None = Field(default=None, max_length=160)
    jira_assignee_display_name: str | None = Field(default=None, max_length=160)
    final_assignee_account_id: str | None = Field(default=None, max_length=160)
    final_assignee_display_name: str | None = Field(default=None, max_length=160)


class JiraImportError(BaseModel):
    row_number: int
    field: str
    message: str
    fix: str


class JiraImportPreview(BaseModel):
    rows: list[JiraImportRow] = Field(default_factory=list)
    errors: list[JiraImportError] = Field(default_factory=list)
    source_count: int = 0
    saved_count: int = 0
    skipped_count: int = 0


class TicketImportResult(BaseModel):
    tickets: list[Ticket]
    imported_count: int = 0
    replaced_count: int = 0
    skipped_count: int = 0


class JiraConnectionCreate(BaseModel):
    site_url: str = Field(min_length=1, max_length=500)
    email: str = Field(min_length=3, max_length=320)
    api_token: str = Field(min_length=1, max_length=2000)
    story_points_field_id: str | None = Field(default=None, max_length=80)

    @field_validator("site_url")
    @classmethod
    def validate_site_url(cls, value: str) -> str:
        from urllib.parse import urlparse

        normalized = value.strip().rstrip("/")
        parsed = urlparse(normalized)
        hostname = (parsed.hostname or "").casefold()
        if (
            parsed.scheme != "https"
            or not hostname.endswith(".atlassian.net")
            or parsed.path not in {"", "/"}
            or parsed.query
            or parsed.fragment
            or parsed.username
            or parsed.password
            or parsed.port
        ):
            raise ValueError("Use the HTTPS URL of a Jira Cloud site ending in .atlassian.net")
        return normalized

    @field_validator("email")
    @classmethod
    def normalize_email(cls, value: str) -> str:
        normalized = value.strip().casefold()
        if "@" not in normalized:
            raise ValueError("Enter the email address used by the Jira account")
        return normalized


class JiraField(BaseModel):
    id: str
    name: str


class JiraConnection(BaseModel):
    room_id: UUID
    owner_id: UUID
    site_url: str
    email: str
    jira_account_id: str
    jira_display_name: str
    story_points_field_id: str | None = None
    story_points_fields: list[JiraField] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class JiraConnectionSecret(JiraConnection):
    encrypted_api_token: str


class JiraSearchRequest(BaseModel):
    jql: str = Field(min_length=1, max_length=10_000)
    duplicate_behavior: DuplicateBehavior = "error"

    @field_validator("jql")
    @classmethod
    def normalize_jql(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("Enter a JQL query")
        return normalized


class JiraFieldSelection(BaseModel):
    field_id: str = Field(min_length=1, max_length=80)


class JiraUser(BaseModel):
    account_id: str
    display_name: str
    avatar_url: str | None = None


class FinalAssigneeUpdate(BaseModel):
    account_id: str | None = Field(default=None, max_length=160)
    display_name: str | None = Field(default=None, max_length=160)

    @model_validator(mode="after")
    def require_display_name_for_user(self) -> "FinalAssigneeUpdate":
        if self.account_id and not self.display_name:
            raise ValueError("Provide the Jira assignee display name")
        return self


class JiraWritebackItem(BaseModel):
    ticket_id: UUID
    issue_key: str
    success: bool
    error: str | None = None


class JiraWritebackResult(BaseModel):
    items: list[JiraWritebackItem]
    succeeded_count: int
    failed_count: int
