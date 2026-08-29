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
4. Open **Room settings** to rename the room. Scale and reveal mode can be changed until tickets are added.

FastAPI validates the Supabase JWT and always scopes reads and writes to the authenticated actor. Creating a room and its owner membership is atomic.

## Verification

```bash
cd backend
uv run ruff check .
uv run pytest

cd ../frontend
npm test -- --run
npm run build
```

## Production configuration

Set `APP_ENV=production` and `VITE_APP_ENV=production`, provide all Supabase values from `.env.example`, and configure the deployed frontend URL in both `FRONTEND_ORIGIN` and the Supabase Auth redirect allow-list. The frontend subscribes to room, membership, ticket, and vote changes through Realtime.
