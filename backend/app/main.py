from functools import lru_cache
from typing import Annotated

from fastapi import Depends, FastAPI, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware

from .config import Settings, get_settings
from .models import EstimateUpdate, Room, RoomCreate, Ticket, TicketImport
from .repositories import InMemoryRepository, Repository, SupabaseRepository


@lru_cache
def get_repository() -> Repository:
    settings = get_settings()
    if settings.supabase_url and settings.supabase_service_role_key:
        return SupabaseRepository(settings.supabase_url, settings.supabase_service_role_key)
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

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/api/rooms", response_model=list[Room])
    def list_rooms(repository: RepositoryDep) -> list[Room]:
        return repository.list_rooms()

    @app.post("/api/rooms", response_model=Room, status_code=status.HTTP_201_CREATED)
    def create_room(payload: RoomCreate, repository: RepositoryDep) -> Room:
        return repository.create_room(payload)

    @app.get("/api/rooms/{room_id}/tickets", response_model=list[Ticket])
    def list_tickets(room_id: str, repository: RepositoryDep) -> list[Ticket]:
        return repository.list_tickets(room_id)

    @app.post("/api/rooms/{room_id}/tickets/import", response_model=list[Ticket])
    def import_tickets(room_id: str, payload: TicketImport, repository: RepositoryDep) -> list[Ticket]:
        return repository.import_tickets(room_id, payload.tickets)

    @app.patch("/api/tickets/{ticket_id}/estimate", response_model=Ticket)
    def update_estimate(
        ticket_id: str, payload: EstimateUpdate, repository: RepositoryDep
    ) -> Ticket:
        ticket = repository.update_estimate(ticket_id, payload.story_points)
        if not ticket:
            raise HTTPException(status_code=404, detail="Ticket not found")
        return ticket

    return app


app = create_app()
