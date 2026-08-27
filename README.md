# tickettalks

Planning-poker skeleton for pricing product stories in focused team sessions.

## Stack

- React 19 + Vite (plain JavaScript and CSS)
- FastAPI + Pydantic
- Supabase Postgres, Auth, Realtime, and row-level security

The app works in demo mode without Supabase credentials. In that mode the API uses an in-memory repository and the frontend falls back to seeded data if the API is not running.

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

Copy `.env.example` to `.env` and add Supabase values when the project is ready. Apply [`supabase/migrations/0001_initial.sql`](supabase/migrations/0001_initial.sql) through the Supabase SQL editor or CLI.

## First production steps

1. Enable Supabase email or SSO auth and replace the demo user in the frontend with `supabase.auth.getSession()`.
2. Use the authenticated user's JWT when calling FastAPI and validate it in an API dependency.
3. Subscribe to `votes` and `room_members` through Supabase Realtime.
4. Move CSV parsing to a background task for large Jira exports.

