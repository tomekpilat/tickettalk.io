import csv
import io
import re
from datetime import UTC, datetime
from uuid import UUID

from fastapi import FastAPI, HTTPException, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, Response

from .auth import Principal, PrincipalDep
from .config import Settings, get_settings
from .dependencies import (
    RepositoryDep,
    get_jira_client_factory,
    get_jira_oauth_client,
    get_repository,
    get_token_cipher,
)
from .jira import parse_jira_import
from .jira_client import JiraError
from .jira_routes import oauth_router as jira_oauth_router
from .jira_routes import router as jira_router
from .models import (
    ActiveTicketUpdate,
    FinalEstimateUpdate,
    JiraImportPreview,
    JiraImportRequest,
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
    NotFoundError,
    Repository,
)

__all__ = [
    "app",
    "create_app",
    "get_jira_client_factory",
    "get_jira_oauth_client",
    "get_repository",
    "get_token_cipher",
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

    app.include_router(jira_router)
    app.include_router(jira_oauth_router)

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
            raise HTTPException(
                status_code=503, detail="A required service is unavailable"
            ) from None
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
