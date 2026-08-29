import csv
import io
import re
from collections.abc import Callable
from datetime import UTC, datetime
from functools import lru_cache
from typing import Annotated
from uuid import UUID

from fastapi import Depends, FastAPI, HTTPException, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, Response

from .auth import Principal, PrincipalDep
from .config import Settings, get_settings
from .jira import parse_jira_import, preview_jira_rows
from .jira_client import JiraClient, JiraError, TokenCipher, field_ids
from .models import (
    ActiveTicketUpdate,
    FinalAssigneeUpdate,
    FinalEstimateUpdate,
    JiraConnection,
    JiraConnectionCreate,
    JiraConnectionSecret,
    JiraFieldSelection,
    JiraImportPreview,
    JiraImportRequest,
    JiraSearchRequest,
    JiraUser,
    JiraWritebackItem,
    JiraWritebackResult,
    Room,
    RoomCreate,
    RoomJoin,
    RoomMember,
    RoomUpdate,
    Ticket,
    TicketCreate,
    TicketImportResult,
    TicketOrder,
    TicketUpdate,
    VoteReceipt,
    VoteResults,
    VoteSubmission,
)
from .observability import RequestContextMiddleware, event_logger, log_event
from .repositories import (
    ConflictError,
    ForbiddenError,
    InMemoryRepository,
    NotFoundError,
    Repository,
    SupabaseRepository,
)


@lru_cache
def get_repository() -> Repository:
    settings = get_settings()
    if settings.supabase_configured:
        return SupabaseRepository(
            settings.supabase_url or "", settings.supabase_service_role_key or ""
        )
    return InMemoryRepository()


RepositoryDep = Annotated[Repository, Depends(get_repository)]


def get_token_cipher() -> TokenCipher:
    key = get_settings().jira_encryption_key
    if not key:
        raise HTTPException(
            status_code=503,
            detail="Jira integration requires JIRA_ENCRYPTION_KEY",
        )
    try:
        return TokenCipher(key)
    except ValueError as error:
        raise HTTPException(status_code=503, detail=str(error)) from error


def get_jira_client_factory() -> Callable[[str, str, str], JiraClient]:
    return JiraClient


TokenCipherDep = Annotated[TokenCipher, Depends(get_token_cipher)]
JiraClientFactoryDep = Annotated[
    Callable[[str, str, str], JiraClient], Depends(get_jira_client_factory)
]


def create_app(settings: Settings | None = None) -> FastAPI:
    config = settings or get_settings()
    app = FastAPI(title=config.app_name, version="0.1.0")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[config.frontend_origin],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
        expose_headers=[
            "Content-Disposition",
            "Retry-After",
            "X-RateLimit-Limit",
            "X-Request-ID",
        ],
    )
    app.add_middleware(
        RequestContextMiddleware,
        join_limit=config.rate_limit_join_per_minute,
        import_limit=config.rate_limit_import_per_minute,
        vote_limit=config.rate_limit_vote_per_minute,
    )

    @app.exception_handler(NotFoundError)
    async def not_found_handler(_: Request, error: NotFoundError) -> JSONResponse:
        return JSONResponse(status_code=404, content={"detail": str(error)})

    @app.exception_handler(ForbiddenError)
    async def forbidden_handler(_: Request, error: ForbiddenError) -> JSONResponse:
        return JSONResponse(status_code=403, content={"detail": str(error)})

    @app.exception_handler(ConflictError)
    async def conflict_handler(_: Request, error: ConflictError) -> JSONResponse:
        return JSONResponse(status_code=409, content={"detail": str(error)})

    @app.exception_handler(JiraError)
    async def jira_error_handler(_: Request, error: JiraError) -> JSONResponse:
        return JSONResponse(status_code=502, content={"detail": str(error)})

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/health/ready")
    def readiness(request: Request, repository: RepositoryDep) -> dict[str, str]:
        try:
            repository.healthcheck()
        except Exception:  # noqa: BLE001 -- readiness is the dependency boundary
            log_event(
                event_logger,
                "readiness_failed",
                request_id=request.state.request_id,
                dependency="supabase",
            )
            raise HTTPException(status_code=503, detail="A required service is unavailable")
        return {"status": "ready"}

    @app.get("/api/me", response_model=Principal)
    def current_user(actor: PrincipalDep) -> Principal:
        return actor

    @app.get("/api/rooms", response_model=list[Room])
    def list_rooms(repository: RepositoryDep, actor: PrincipalDep) -> list[Room]:
        return repository.list_rooms(actor)

    @app.post("/api/rooms", response_model=Room, status_code=status.HTTP_201_CREATED)
    def create_room(
        payload: RoomCreate, repository: RepositoryDep, actor: PrincipalDep
    ) -> Room:
        return repository.create_room(payload, actor)

    @app.get("/api/rooms/{room_id}", response_model=Room)
    def get_room(
        room_id: UUID, repository: RepositoryDep, actor: PrincipalDep
    ) -> Room:
        return repository.get_room(room_id, actor)

    @app.patch("/api/rooms/{room_id}", response_model=Room)
    def update_room(
        room_id: UUID,
        payload: RoomUpdate,
        repository: RepositoryDep,
        actor: PrincipalDep,
    ) -> Room:
        return repository.update_room(room_id, payload, actor)

    @app.patch("/api/rooms/{room_id}/active-ticket", response_model=Room)
    def set_active_ticket(
        room_id: UUID,
        payload: ActiveTicketUpdate,
        repository: RepositoryDep,
        actor: PrincipalDep,
    ) -> Room:
        return repository.set_active_ticket(room_id, payload.ticket_id, actor)

    @app.get("/api/rooms/{room_id}/export")
    def export_room(
        room_id: UUID, repository: RepositoryDep, actor: PrincipalDep
    ) -> Response:
        room, tickets = repository.export_room(room_id, actor)
        output = io.StringIO(newline="")
        writer = csv.writer(output, lineterminator="\r\n")
        writer.writerow(
            [
                "Jira key",
                "Summary",
                "Issue type",
                "Description",
                "Original story points",
                "Final Tickettalk estimate",
            ]
        )
        for ticket in tickets:
            writer.writerow(
                [
                    ticket.issue_key or "",
                    ticket.summary,
                    ticket.issue_type,
                    ticket.description,
                    "" if ticket.story_points is None else ticket.story_points,
                    ticket.final_estimate or "",
                ]
            )
        slug = re.sub(r"[^a-z0-9]+", "-", room.name.casefold()).strip("-") or "room"
        filename = f"{slug}-{datetime.now(UTC).date().isoformat()}.csv"
        return Response(
            output.getvalue(),
            media_type="text/csv",
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )

    @app.delete("/api/rooms/{room_id}", status_code=status.HTTP_204_NO_CONTENT)
    def delete_room(
        room_id: UUID,
        request: Request,
        repository: RepositoryDep,
        actor: PrincipalDep,
    ) -> None:
        repository.delete_room(room_id, actor)
        log_event(
            event_logger,
            "room_deleted",
            request_id=request.state.request_id,
            room_id=room_id,
            owner_id=actor.id,
        )

    @app.post("/api/rooms/{room_id}/join", response_model=RoomMember)
    def join_room(
        room_id: UUID,
        payload: RoomJoin,
        repository: RepositoryDep,
        actor: PrincipalDep,
    ) -> RoomMember:
        return repository.join_room(room_id, payload, actor)

    @app.get("/api/rooms/{room_id}/members", response_model=list[RoomMember])
    def list_members(
        room_id: UUID, repository: RepositoryDep, actor: PrincipalDep
    ) -> list[RoomMember]:
        return repository.list_members(room_id, actor)

    @app.post("/api/rooms/{room_id}/presence", response_model=RoomMember)
    def touch_presence(
        room_id: UUID, repository: RepositoryDep, actor: PrincipalDep
    ) -> RoomMember:
        return repository.touch_presence(room_id, actor)

    @app.put(
        "/api/rooms/{room_id}/tickets/{ticket_id}/vote",
        response_model=VoteReceipt,
    )
    def submit_vote(
        room_id: UUID,
        ticket_id: UUID,
        payload: VoteSubmission,
        repository: RepositoryDep,
        actor: PrincipalDep,
    ) -> VoteReceipt:
        return repository.submit_vote(room_id, ticket_id, payload.value, actor)

    @app.get(
        "/api/rooms/{room_id}/tickets/{ticket_id}/votes",
        response_model=VoteResults,
    )
    def get_vote_results(
        room_id: UUID,
        ticket_id: UUID,
        repository: RepositoryDep,
        actor: PrincipalDep,
    ) -> VoteResults:
        return repository.get_vote_results(room_id, ticket_id, actor)

    @app.post(
        "/api/rooms/{room_id}/tickets/{ticket_id}/reveal",
        response_model=VoteResults,
    )
    def reveal_votes(
        room_id: UUID,
        ticket_id: UUID,
        repository: RepositoryDep,
        actor: PrincipalDep,
    ) -> VoteResults:
        return repository.reveal_votes(room_id, ticket_id, actor)

    @app.post(
        "/api/rooms/{room_id}/tickets/{ticket_id}/revote",
        response_model=VoteResults,
    )
    def restart_vote(
        room_id: UUID,
        ticket_id: UUID,
        repository: RepositoryDep,
        actor: PrincipalDep,
    ) -> VoteResults:
        return repository.restart_vote(room_id, ticket_id, actor)

    @app.put(
        "/api/rooms/{room_id}/tickets/{ticket_id}/final-estimate",
        response_model=Ticket,
    )
    def set_final_estimate(
        room_id: UUID,
        ticket_id: UUID,
        payload: FinalEstimateUpdate,
        repository: RepositoryDep,
        actor: PrincipalDep,
    ) -> Ticket:
        return repository.set_final_estimate(room_id, ticket_id, payload.value, actor)

    @app.get("/api/rooms/{room_id}/tickets", response_model=list[Ticket])
    def list_tickets(
        room_id: UUID, repository: RepositoryDep, actor: PrincipalDep
    ) -> list[Ticket]:
        return repository.list_tickets(room_id, actor)

    def import_preview(
        room_id: UUID,
        payload: JiraImportRequest,
        repository: Repository,
        actor: Principal,
    ) -> JiraImportPreview:
        room = repository.get_room(room_id, actor)
        if room.owner_id != actor.id:
            raise ForbiddenError("Only the facilitator can change the backlog")
        return parse_jira_import(
            payload.content,
            payload.duplicate_behavior,
            repository.list_tickets(room_id, actor),
        )

    @app.post(
        "/api/rooms/{room_id}/tickets/import/preview",
        response_model=JiraImportPreview,
    )
    def preview_ticket_import(
        room_id: UUID,
        payload: JiraImportRequest,
        repository: RepositoryDep,
        actor: PrincipalDep,
    ) -> JiraImportPreview:
        return import_preview(room_id, payload, repository, actor)

    @app.post(
        "/api/rooms/{room_id}/tickets/import", response_model=TicketImportResult
    )
    def import_tickets(
        room_id: UUID,
        payload: JiraImportRequest,
        repository: RepositoryDep,
        actor: PrincipalDep,
    ) -> TicketImportResult:
        preview = import_preview(room_id, payload, repository, actor)
        if preview.errors:
            raise HTTPException(
                status_code=422,
                detail=[error.model_dump() for error in preview.errors],
            )
        return repository.import_tickets(room_id, preview.rows, actor)

    def jira_rows(
        room_id: UUID,
        payload: JiraSearchRequest,
        repository: Repository,
        actor: Principal,
        cipher: TokenCipher,
        client_factory: Callable[[str, str, str], JiraClient],
    ) -> JiraImportPreview:
        connection = repository.get_jira_connection(room_id, actor)
        token = cipher.decrypt(connection.encrypted_api_token)
        with client_factory(connection.site_url, connection.email, token) as jira:
            rows = jira.search(payload.jql, connection.story_points_field_id)
        for row in rows:
            row.jira_site_url = connection.site_url
        return preview_jira_rows(
            rows,
            payload.duplicate_behavior,
            repository.list_tickets(room_id, actor),
        )

    @app.post(
        "/api/rooms/{room_id}/jira/connection",
        response_model=JiraConnection,
    )
    def connect_jira(
        room_id: UUID,
        payload: JiraConnectionCreate,
        repository: RepositoryDep,
        actor: PrincipalDep,
        cipher: TokenCipherDep,
        client_factory: JiraClientFactoryDep,
    ) -> JiraConnection:
        room = repository.get_room(room_id, actor)
        if room.owner_id != actor.id:
            raise ForbiddenError("Only the facilitator can connect Jira")
        with client_factory(payload.site_url, payload.email, payload.api_token) as jira:
            identity = jira.myself()
            points_fields = jira.story_points_fields()
        if not points_fields:
            raise HTTPException(
                status_code=422,
                detail="No Jira Story Points field was found for this account",
            )
        selected_field = payload.story_points_field_id
        if selected_field and selected_field not in field_ids(points_fields):
            raise HTTPException(
                status_code=422,
                detail="The selected Story Points field was not found on this Jira site",
            )
        if not selected_field and points_fields:
            selected_field = points_fields[0].id
        now = datetime.now(UTC)
        return repository.save_jira_connection(
            JiraConnectionSecret(
                room_id=room_id,
                owner_id=actor.id,
                site_url=payload.site_url,
                email=payload.email,
                encrypted_api_token=cipher.encrypt(payload.api_token),
                jira_account_id=identity["account_id"],
                jira_display_name=identity["display_name"],
                story_points_field_id=selected_field,
                story_points_fields=points_fields,
                created_at=now,
                updated_at=now,
            ),
            actor,
        ).model_copy(update={"story_points_fields": points_fields})

    @app.get(
        "/api/rooms/{room_id}/jira/connection",
        response_model=JiraConnection,
    )
    def get_jira_connection(
        room_id: UUID, repository: RepositoryDep, actor: PrincipalDep
    ) -> JiraConnection:
        connection = repository.get_jira_connection(room_id, actor)
        return JiraConnection.model_validate(
            connection.model_dump(exclude={"encrypted_api_token"})
        )

    @app.put(
        "/api/rooms/{room_id}/jira/connection/story-points-field",
        response_model=JiraConnection,
    )
    def select_jira_story_points_field(
        room_id: UUID,
        payload: JiraFieldSelection,
        repository: RepositoryDep,
        actor: PrincipalDep,
    ) -> JiraConnection:
        connection = repository.get_jira_connection(room_id, actor)
        if payload.field_id not in field_ids(connection.story_points_fields):
            raise HTTPException(
                status_code=422,
                detail="The selected Story Points field is not available",
            )
        updated = connection.model_copy(
            update={"story_points_field_id": payload.field_id}
        )
        return repository.save_jira_connection(updated, actor).model_copy(
            update={"story_points_fields": connection.story_points_fields}
        )

    @app.delete(
        "/api/rooms/{room_id}/jira/connection",
        status_code=status.HTTP_204_NO_CONTENT,
    )
    def disconnect_jira(
        room_id: UUID, repository: RepositoryDep, actor: PrincipalDep
    ) -> None:
        repository.delete_jira_connection(room_id, actor)

    @app.post(
        "/api/rooms/{room_id}/jira/search",
        response_model=JiraImportPreview,
    )
    def preview_jira_search(
        room_id: UUID,
        payload: JiraSearchRequest,
        repository: RepositoryDep,
        actor: PrincipalDep,
        cipher: TokenCipherDep,
        client_factory: JiraClientFactoryDep,
    ) -> JiraImportPreview:
        return jira_rows(
            room_id, payload, repository, actor, cipher, client_factory
        )

    @app.post(
        "/api/rooms/{room_id}/jira/import",
        response_model=TicketImportResult,
    )
    def import_jira_search(
        room_id: UUID,
        payload: JiraSearchRequest,
        repository: RepositoryDep,
        actor: PrincipalDep,
        cipher: TokenCipherDep,
        client_factory: JiraClientFactoryDep,
    ) -> TicketImportResult:
        preview = jira_rows(
            room_id, payload, repository, actor, cipher, client_factory
        )
        if preview.errors:
            raise HTTPException(
                status_code=422,
                detail=[error.model_dump() for error in preview.errors],
            )
        return repository.import_tickets(room_id, preview.rows, actor)

    @app.get(
        "/api/rooms/{room_id}/tickets/{ticket_id}/jira-assignees",
        response_model=list[JiraUser],
    )
    def list_jira_assignees(
        room_id: UUID,
        ticket_id: UUID,
        repository: RepositoryDep,
        actor: PrincipalDep,
        cipher: TokenCipherDep,
        client_factory: JiraClientFactoryDep,
        q: str = "",
    ) -> list[JiraUser]:
        connection = repository.get_jira_connection(room_id, actor)
        ticket = next(
            (
                item
                for item in repository.list_tickets(room_id, actor)
                if item.id == ticket_id
            ),
            None,
        )
        if (
            not ticket
            or not ticket.issue_key
            or not ticket.jira_issue_id
            or ticket.jira_site_url != connection.site_url
        ):
            raise NotFoundError("Jira ticket not found")
        token = cipher.decrypt(connection.encrypted_api_token)
        with client_factory(connection.site_url, connection.email, token) as jira:
            return jira.assignable_users(ticket.issue_key, q.strip())

    @app.put(
        "/api/rooms/{room_id}/tickets/{ticket_id}/jira-assignee",
        response_model=Ticket,
    )
    def set_jira_final_assignee(
        room_id: UUID,
        ticket_id: UUID,
        payload: FinalAssigneeUpdate,
        repository: RepositoryDep,
        actor: PrincipalDep,
    ) -> Ticket:
        return repository.set_final_assignee(
            room_id,
            ticket_id,
            payload.account_id,
            payload.display_name,
            actor,
        )

    @app.post(
        "/api/rooms/{room_id}/jira/writeback",
        response_model=JiraWritebackResult,
    )
    def writeback_jira(
        room_id: UUID,
        repository: RepositoryDep,
        actor: PrincipalDep,
        cipher: TokenCipherDep,
        client_factory: JiraClientFactoryDep,
    ) -> JiraWritebackResult:
        room = repository.get_room(room_id, actor)
        if room.owner_id != actor.id:
            raise ForbiddenError("Only the facilitator can write results to Jira")
        if room.scale == "tshirt":
            raise ConflictError("T-shirt estimates cannot be written to numeric Jira Story Points")
        connection = repository.get_jira_connection(room_id, actor)
        if not connection.story_points_field_id:
            raise ConflictError("Reconnect Jira after configuring a Story Points field")
        tickets = [
            ticket
            for ticket in repository.list_tickets(room_id, actor)
            if ticket.jira_issue_id and ticket.issue_key
        ]
        if not tickets:
            raise ConflictError("This room has no Jira tickets")
        if any(ticket.final_estimate is None for ticket in tickets):
            raise ConflictError("Set a final estimate for every Jira ticket before write-back")
        if any(ticket.jira_site_url != connection.site_url for ticket in tickets):
            raise ConflictError("Reconnect the Jira site used to import these tickets")

        token = cipher.decrypt(connection.encrypted_api_token)
        items: list[JiraWritebackItem] = []
        with client_factory(connection.site_url, connection.email, token) as jira:
            for ticket in tickets:
                try:
                    estimate = float(ticket.final_estimate or "")
                    jira.write_issue(
                        ticket.issue_key or "",
                        connection.story_points_field_id,
                        estimate,
                        ticket.final_assignee_account_id,
                    )
                    repository.record_jira_writeback(
                        room_id, ticket.id, None, actor
                    )
                    items.append(
                        JiraWritebackItem(
                            ticket_id=ticket.id,
                            issue_key=ticket.issue_key or "",
                            success=True,
                        )
                    )
                except (JiraError, ValueError) as error:
                    message = str(error) or "The final estimate is not numeric"
                    repository.record_jira_writeback(
                        room_id, ticket.id, message, actor
                    )
                    items.append(
                        JiraWritebackItem(
                            ticket_id=ticket.id,
                            issue_key=ticket.issue_key or "",
                            success=False,
                            error=message,
                        )
                    )
        succeeded = sum(item.success for item in items)
        return JiraWritebackResult(
            items=items,
            succeeded_count=succeeded,
            failed_count=len(items) - succeeded,
        )

    @app.post(
        "/api/rooms/{room_id}/tickets",
        response_model=Ticket,
        status_code=status.HTTP_201_CREATED,
    )
    def create_ticket(
        room_id: UUID,
        payload: TicketCreate,
        repository: RepositoryDep,
        actor: PrincipalDep,
    ) -> Ticket:
        return repository.create_ticket(room_id, payload, actor)

    @app.patch("/api/rooms/{room_id}/tickets/{ticket_id}", response_model=Ticket)
    def update_ticket(
        room_id: UUID,
        ticket_id: UUID,
        payload: TicketUpdate,
        repository: RepositoryDep,
        actor: PrincipalDep,
    ) -> Ticket:
        return repository.update_ticket(room_id, ticket_id, payload, actor)

    @app.delete(
        "/api/rooms/{room_id}/tickets/{ticket_id}",
        status_code=status.HTTP_204_NO_CONTENT,
    )
    def delete_ticket(
        room_id: UUID,
        ticket_id: UUID,
        repository: RepositoryDep,
        actor: PrincipalDep,
    ) -> None:
        repository.delete_ticket(room_id, ticket_id, actor)

    @app.put("/api/rooms/{room_id}/tickets/order", response_model=list[Ticket])
    def reorder_tickets(
        room_id: UUID,
        payload: TicketOrder,
        repository: RepositoryDep,
        actor: PrincipalDep,
    ) -> list[Ticket]:
        return repository.reorder_tickets(room_id, payload.ticket_ids, actor)

    return app


app = create_app()
