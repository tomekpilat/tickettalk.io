from functools import lru_cache
from typing import Annotated
from uuid import UUID

from fastapi import Depends, FastAPI, HTTPException, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from .auth import Principal, PrincipalDep
from .config import Settings, get_settings
from .models import EstimateUpdate, Room, RoomCreate, RoomUpdate, Ticket, TicketImport
from .repositories import (
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


def create_app(settings: Settings | None = None) -> FastAPI:
    config = settings or get_settings()
    app = FastAPI(title=config.app_name, version="0.1.0")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[config.frontend_origin],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.exception_handler(NotFoundError)
    async def not_found_handler(_: Request, error: NotFoundError) -> JSONResponse:
        return JSONResponse(status_code=404, content={"detail": str(error)})

    @app.exception_handler(ForbiddenError)
    async def forbidden_handler(_: Request, error: ForbiddenError) -> JSONResponse:
        return JSONResponse(status_code=403, content={"detail": str(error)})

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

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

    @app.get("/api/rooms/{room_id}/tickets", response_model=list[Ticket])
    def list_tickets(
        room_id: UUID, repository: RepositoryDep, actor: PrincipalDep
    ) -> list[Ticket]:
        return repository.list_tickets(room_id, actor)

    @app.post("/api/rooms/{room_id}/tickets/import", response_model=list[Ticket])
    def import_tickets(
        room_id: UUID,
        payload: TicketImport,
        repository: RepositoryDep,
        actor: PrincipalDep,
    ) -> list[Ticket]:
        return repository.import_tickets(room_id, payload.tickets, actor)

    @app.patch("/api/tickets/{ticket_id}/estimate", response_model=Ticket)
    def update_estimate(
        ticket_id: UUID,
        payload: EstimateUpdate,
        repository: RepositoryDep,
        actor: PrincipalDep,
    ) -> Ticket:
        ticket = repository.update_estimate(ticket_id, payload.story_points, actor)
        if not ticket:
            raise HTTPException(status_code=404, detail="Ticket not found")
        return ticket

    return app


app = create_app()
