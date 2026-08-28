# tickettalks

Planning poker for pricing product stories in focused team sessions.

## Stack

- React 19 + Vite (plain JavaScript and CSS)
- FastAPI + Pydantic
- Supabase Postgres, Auth, Realtime, and row-level security

In development, the app can run without Supabase credentials by using a fixed local facilitator and an in-memory repository. Production refuses to start without Supabase credentials and never enables the development identity.

## Run locally

### API

```bash
cd backend
uv sync
uv run uvicorn app.main:app --reload
```

### Web app

```bash
cd frontend
npm install
npm run dev
```

Copy `.env.example` to `.env`. Without Supabase values, the web app sends the development-only token configured by `VITE_DEMO_AUTH_TOKEN`; keep it equal to the API's `DEMO_AUTH_TOKEN`.

### Local Supabase

```bash
supabase start
supabase db reset
supabase test db
```

Copy the local API URL, anon key, and service-role key printed by `supabase status` into `.env`, then restart both apps. The browser uses passwordless email sign-in; room members can use Supabase anonymous Auth in the member-join flow.

The initial migration creates profiles, rooms, memberships, tickets, and votes; enables RLS and Realtime; and adds the `create_room_with_facilitator` transaction used by FastAPI. The pgTAP suite in `supabase/tests/rls.sql` checks cross-room isolation and hidden votes.

## Room workflow

1. Sign in as a facilitator (or use the development identity).
2. Create a room with a name, estimation scale, and reveal mode.
3. Share the canonical `/rooms/<uuid>` URL.
4. A teammate opens that URL, enters a display name, and receives a persistent anonymous membership for that browser.
5. Open **Room settings** to rename the room. Scale and reveal mode can be changed until tickets are added.

Room clients send a presence heartbeat every 15 seconds. Members are shown as disconnected after 45 seconds without a heartbeat, so abandoned browser sessions do not remain online indefinitely.

Votes are submitted through FastAPI and the response never includes the selected value. Before reveal, Supabase RLS lets a voter read only their own vote, while the browser subscribes to the separate `vote_statuses` table containing user/ticket identity and timestamps but no vote value. Raw `votes` are not part of the Realtime publication.

Manual and automatic reveal share a durable ticket-round state. Automatic mode counts members seen within the 45-second presence window and reveals atomically when the last eligible vote arrives. Re-vote clears prior values, increments the round, and clears the prior final estimate; numeric summaries and final estimates are restored after reconnect.

Facilitators can download an authorized server-side CSV containing Jira metadata, original story points, and final Tickettalks estimates. Room deletion requires typing the exact room name and cascades through memberships, tickets, safe vote statuses, and private votes; the API logs only room and owner identifiers for the deletion event.

Jira imports accept CSV, TSV, pasted text, quoted commas, and multiline descriptions. Imports are limited to 1 MB and 500 tickets, validated by the API before saving, and require an explicit skip-or-replace choice for Jira keys already in the room. Facilitators can also add tickets without a Jira key and edit, reorder, or remove every backlog item; members retain read-only access.

FastAPI validates the Supabase JWT and always scopes reads and writes to the authenticated actor. Creating a room and its owner membership is atomic.

## Verification

```bash
cd backend
uv run ruff check .
uv run pytest --cov --cov-report=term-missing

cd ../frontend
npm run lint
npm run test:coverage
npm run build
```

## Production configuration

Set `APP_ENV=production` and `VITE_APP_ENV=production`, provide all Supabase values from `.env.example`, and configure the deployed frontend URL in both `FRONTEND_ORIGIN` and the Supabase Auth redirect allow-list. The frontend subscribes to room, membership, ticket, and vote changes through Realtime.

The production Compose topology and Coolify setup are documented in [`docs/deployment.md`](docs/deployment.md). Monitoring, incidents, restore drills, log safety, rate limits, and retention are in [`docs/operations.md`](docs/operations.md); production sign-off uses [`docs/release-checklist.md`](docs/release-checklist.md).
