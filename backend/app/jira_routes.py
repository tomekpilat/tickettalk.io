from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from uuid import UUID

from fastapi import APIRouter, HTTPException, status

from .auth import Principal, PrincipalDep
from .dependencies import (
    JiraClientFactoryDep,
    JiraOAuthClientDep,
    RepositoryDep,
    TokenCipherDep,
)
from .jira import preview_jira_rows
from .jira_client import JiraClient, JiraError, TokenCipher, field_ids
from .jira_oauth import AtlassianOAuthClient
from .models import (
    FinalAssigneeUpdate,
    JiraConnection,
    JiraConnectionCreate,
    JiraConnectionSecret,
    JiraFieldSelection,
    JiraImportPreview,
    JiraOAuthAuthorizeRequest,
    JiraOAuthAuthorizeResponse,
    JiraOAuthCallbackRequest,
    JiraOAuthCallbackResult,
    JiraSearchRequest,
    JiraUser,
    JiraWritebackItem,
    JiraWritebackResult,
    Ticket,
    TicketImportResult,
)
from .repositories import ConflictError, ForbiddenError, NotFoundError, Repository

router = APIRouter(prefix="/api/rooms/{room_id}", tags=["jira"])
oauth_router = APIRouter(prefix="/api/jira", tags=["jira"])

SECRET_FIELDS = {
    "auth_method",
    "cloud_id",
    "encrypted_api_token",
    "encrypted_access_token",
    "encrypted_refresh_token",
    "token_expires_at",
}


def _require_facilitator(
    room_id: UUID, repository: Repository, actor: Principal, action: str
) -> None:
    if repository.get_room(room_id, actor).owner_id != actor.id:
        raise ForbiddenError(f"Only the facilitator can {action}")


def _public_connection(connection: JiraConnectionSecret) -> JiraConnection:
    return JiraConnection.model_validate(
        connection.model_dump(exclude=SECRET_FIELDS) | {"oauth": connection.auth_method == "oauth"}
    )


def _client(
    connection: JiraConnectionSecret,
    cipher: TokenCipher,
    client_factory: Callable[[str, str | None, str], JiraClient],
    oauth_client: AtlassianOAuthClient,
    repository: Repository,
    actor: Principal,
) -> tuple[JiraConnectionSecret, JiraClient]:
    if connection.auth_method == "api_token":
        if not connection.email or not connection.encrypted_api_token:
            raise JiraError("The stored Jira API-token connection is incomplete; reconnect Jira")
        return connection, client_factory(
            connection.site_url,
            connection.email,
            cipher.decrypt(connection.encrypted_api_token),
        )

    if not (
        connection.cloud_id
        and connection.encrypted_access_token
        and connection.encrypted_refresh_token
        and connection.token_expires_at
    ):
        raise JiraError("The stored Jira OAuth connection is incomplete; reconnect Jira")

    if connection.token_expires_at <= datetime.now(UTC) + timedelta(seconds=60):
        tokens = oauth_client.refresh(cipher.decrypt(connection.encrypted_refresh_token))
        connection = connection.model_copy(
            update={
                "encrypted_access_token": cipher.encrypt(tokens.access_token),
                "encrypted_refresh_token": cipher.encrypt(tokens.refresh_token),
                "token_expires_at": tokens.expires_at,
                "updated_at": datetime.now(UTC),
            }
        )
        repository.save_jira_connection(connection, actor)

    return connection, client_factory(
        oauth_client.jira_api_url(connection.cloud_id),
        None,
        cipher.decrypt(connection.encrypted_access_token),
    )


def _jira_preview(
    room_id: UUID,
    payload: JiraSearchRequest,
    repository: Repository,
    actor: Principal,
    cipher: TokenCipher,
    client_factory: Callable[[str, str | None, str], JiraClient],
    oauth_client: AtlassianOAuthClient,
) -> JiraImportPreview:
    connection = repository.get_jira_connection(room_id, actor)
    connection, jira = _client(connection, cipher, client_factory, oauth_client, repository, actor)
    with jira:
        rows = jira.search(payload.jql, connection.story_points_field_id)
    for row in rows:
        row.jira_site_url = connection.site_url
    return preview_jira_rows(
        rows,
        payload.duplicate_behavior,
        repository.list_tickets(room_id, actor),
    )


@router.post("/jira/connection", response_model=JiraConnection)
def connect_jira(
    room_id: UUID,
    payload: JiraConnectionCreate,
    repository: RepositoryDep,
    actor: PrincipalDep,
    cipher: TokenCipherDep,
    client_factory: JiraClientFactoryDep,
) -> JiraConnection:
    _require_facilitator(room_id, repository, actor, "connect Jira")
    with client_factory(payload.site_url, payload.email, payload.api_token) as jira:
        identity = jira.myself()
        points_fields = jira.story_points_fields()
    if not points_fields:
        raise HTTPException(
            status_code=422,
            detail="No Jira Story Points field was found for this account",
        )
    selected_field = payload.story_points_field_id or points_fields[0].id
    if selected_field not in field_ids(points_fields):
        raise HTTPException(
            status_code=422,
            detail="The selected Story Points field was not found on this Jira site",
        )
    now = datetime.now(UTC)
    saved = repository.save_jira_connection(
        JiraConnectionSecret(
            room_id=room_id,
            owner_id=actor.id,
            site_url=payload.site_url,
            auth_method="api_token",
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
    )
    return saved.model_copy(update={"story_points_fields": points_fields})


@router.post("/jira/oauth/authorize", response_model=JiraOAuthAuthorizeResponse)
def authorize_jira_oauth(
    room_id: UUID,
    payload: JiraOAuthAuthorizeRequest,
    repository: RepositoryDep,
    actor: PrincipalDep,
    cipher: TokenCipherDep,
    oauth_client: JiraOAuthClientDep,
) -> JiraOAuthAuthorizeResponse:
    _require_facilitator(room_id, repository, actor, "connect Jira")
    state = cipher.encrypt_state(
        {
            "room_id": str(room_id),
            "owner_id": str(actor.id),
            "site_url": payload.site_url,
        }
    )
    return JiraOAuthAuthorizeResponse(authorization_url=oauth_client.authorization_url(state))


@oauth_router.post("/oauth/callback", response_model=JiraOAuthCallbackResult)
def complete_jira_oauth(
    payload: JiraOAuthCallbackRequest,
    repository: RepositoryDep,
    actor: PrincipalDep,
    cipher: TokenCipherDep,
    client_factory: JiraClientFactoryDep,
    oauth_client: JiraOAuthClientDep,
) -> JiraOAuthCallbackResult:
    state = cipher.decrypt_state(payload.state)
    if state.get("owner_id") != str(actor.id):
        raise ForbiddenError("This Jira authorization belongs to another browser session")
    try:
        room_id = UUID(state["room_id"])
        site_url = JiraOAuthAuthorizeRequest(site_url=state["site_url"]).site_url
    except (KeyError, ValueError) as error:
        raise JiraError("The Jira authorization request is invalid; connect again") from error
    _require_facilitator(room_id, repository, actor, "connect Jira")

    tokens = oauth_client.exchange_code(payload.code)
    matches = [
        resource
        for resource in oauth_client.accessible_resources(tokens.access_token)
        if resource.url.rstrip("/").casefold() == site_url.casefold()
    ]
    if len(matches) != 1:
        raise JiraError(
            "The approved Atlassian account cannot access that Jira site; "
            "connect again with the correct site URL"
        )
    resource = matches[0]
    with client_factory(oauth_client.jira_api_url(resource.id), None, tokens.access_token) as jira:
        identity = jira.myself()
        points_fields = jira.story_points_fields()
    if not points_fields:
        raise HTTPException(
            status_code=422,
            detail="No Jira Story Points field was found for this account",
        )
    now = datetime.now(UTC)
    connection = JiraConnectionSecret(
        room_id=room_id,
        owner_id=actor.id,
        site_url=site_url,
        auth_method="oauth",
        cloud_id=resource.id,
        encrypted_access_token=cipher.encrypt(tokens.access_token),
        encrypted_refresh_token=cipher.encrypt(tokens.refresh_token),
        token_expires_at=tokens.expires_at,
        jira_account_id=identity["account_id"],
        jira_display_name=identity["display_name"],
        story_points_field_id=points_fields[0].id,
        story_points_fields=points_fields,
        created_at=now,
        updated_at=now,
    )
    saved = repository.save_jira_connection(connection, actor)
    return JiraOAuthCallbackResult(
        room_id=room_id,
        connection=saved.model_copy(update={"story_points_fields": points_fields}),
    )


@router.get("/jira/connection", response_model=JiraConnection)
def get_jira_connection(
    room_id: UUID, repository: RepositoryDep, actor: PrincipalDep
) -> JiraConnection:
    return _public_connection(repository.get_jira_connection(room_id, actor))


@router.put("/jira/connection/story-points-field", response_model=JiraConnection)
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
    saved = repository.save_jira_connection(
        connection.model_copy(update={"story_points_field_id": payload.field_id}),
        actor,
    )
    return saved.model_copy(update={"story_points_fields": connection.story_points_fields})


@router.delete("/jira/connection", status_code=status.HTTP_204_NO_CONTENT)
def disconnect_jira(room_id: UUID, repository: RepositoryDep, actor: PrincipalDep) -> None:
    repository.delete_jira_connection(room_id, actor)


@router.post("/jira/search", response_model=JiraImportPreview)
def preview_jira_search(
    room_id: UUID,
    payload: JiraSearchRequest,
    repository: RepositoryDep,
    actor: PrincipalDep,
    cipher: TokenCipherDep,
    client_factory: JiraClientFactoryDep,
    oauth_client: JiraOAuthClientDep,
) -> JiraImportPreview:
    return _jira_preview(room_id, payload, repository, actor, cipher, client_factory, oauth_client)


@router.post("/jira/import", response_model=TicketImportResult)
def import_jira_search(
    room_id: UUID,
    payload: JiraSearchRequest,
    repository: RepositoryDep,
    actor: PrincipalDep,
    cipher: TokenCipherDep,
    client_factory: JiraClientFactoryDep,
    oauth_client: JiraOAuthClientDep,
) -> TicketImportResult:
    preview = _jira_preview(
        room_id, payload, repository, actor, cipher, client_factory, oauth_client
    )
    if preview.errors:
        raise HTTPException(
            status_code=422,
            detail=[error.model_dump() for error in preview.errors],
        )
    return repository.import_tickets(room_id, preview.rows, actor)


def _jira_ticket(
    room_id: UUID,
    ticket_id: UUID,
    site_url: str,
    repository: Repository,
    actor: Principal,
) -> Ticket:
    ticket = next(
        (item for item in repository.list_tickets(room_id, actor) if item.id == ticket_id),
        None,
    )
    if (
        not ticket
        or not ticket.issue_key
        or not ticket.jira_issue_id
        or ticket.jira_site_url != site_url
    ):
        raise NotFoundError("Jira ticket not found")
    return ticket


@router.get("/tickets/{ticket_id}/jira-assignees", response_model=list[JiraUser])
def list_jira_assignees(
    room_id: UUID,
    ticket_id: UUID,
    repository: RepositoryDep,
    actor: PrincipalDep,
    cipher: TokenCipherDep,
    client_factory: JiraClientFactoryDep,
    oauth_client: JiraOAuthClientDep,
    q: str = "",
) -> list[JiraUser]:
    connection = repository.get_jira_connection(room_id, actor)
    ticket = _jira_ticket(room_id, ticket_id, connection.site_url, repository, actor)
    _, jira = _client(connection, cipher, client_factory, oauth_client, repository, actor)
    with jira:
        return jira.assignable_users(ticket.issue_key or "", q.strip())


@router.put("/tickets/{ticket_id}/jira-assignee", response_model=Ticket)
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


def _jira_tickets_for_writeback(
    room_id: UUID,
    repository: Repository,
    actor: Principal,
    connection: JiraConnectionSecret,
) -> list[Ticket]:
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
    return tickets


@router.post("/jira/writeback", response_model=JiraWritebackResult)
def writeback_jira(
    room_id: UUID,
    repository: RepositoryDep,
    actor: PrincipalDep,
    cipher: TokenCipherDep,
    client_factory: JiraClientFactoryDep,
    oauth_client: JiraOAuthClientDep,
) -> JiraWritebackResult:
    room = repository.get_room(room_id, actor)
    if room.owner_id != actor.id:
        raise ForbiddenError("Only the facilitator can write results to Jira")
    if room.scale == "tshirt":
        raise ConflictError("T-shirt estimates cannot be written to numeric Jira Story Points")
    connection = repository.get_jira_connection(room_id, actor)
    if not connection.story_points_field_id:
        raise ConflictError("Reconnect Jira after configuring a Story Points field")
    tickets = _jira_tickets_for_writeback(room_id, repository, actor, connection)

    items: list[JiraWritebackItem] = []
    _, jira = _client(connection, cipher, client_factory, oauth_client, repository, actor)
    with jira:
        for ticket in tickets:
            try:
                jira.write_issue(
                    ticket.issue_key or "",
                    connection.story_points_field_id,
                    float(ticket.final_estimate or ""),
                    ticket.final_assignee_account_id,
                )
                repository.record_jira_writeback(room_id, ticket.id, None, actor)
                items.append(
                    JiraWritebackItem(
                        ticket_id=ticket.id,
                        issue_key=ticket.issue_key or "",
                        success=True,
                    )
                )
            except (JiraError, ValueError) as error:
                message = str(error) or "The final estimate is not numeric"
                repository.record_jira_writeback(room_id, ticket.id, message, actor)
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
