# tickettalk

Planning poker for pricing product stories in focused team sessions.

See [`ARCHITECTURE.md`](ARCHITECTURE.md) for the product architecture, trust boundaries, data model, and end-to-end data flows.

## Stack

- React 19 + Vite (plain JavaScript and CSS)
- FastAPI + Pydantic
- Supabase Postgres, Auth, Realtime, and row-level security

tickettalk requires no registration, email, or password. In production, each browser receives a persistent anonymous Supabase identity. A room's random UUID URL is its private capability link, while the creating browser retains the facilitator role. In development, the app can run without Supabase credentials by using a fixed anonymous facilitator and an in-memory repository. Production refuses to start without Supabase credentials and never enables the development identity.

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

Copy the local API URL, anon key, and service-role key printed by `supabase status` into `.env`, then restart both apps. Enable anonymous Auth. The browser creates an anonymous session automatically; users provide only a display name when creating or joining a room.

The initial migration creates profiles, rooms, memberships, tickets, and votes; enables RLS and Realtime; and adds the `create_room_with_facilitator` transaction used by FastAPI. The pgTAP suite in `supabase/tests/rls.sql` checks cross-room isolation and hidden votes.

## Room workflow

1. Enter a display name and create a room with a name, estimation scale, and reveal mode.
2. tickettalk generates a random UUID and canonical `/rooms/<uuid>` capability URL.
3. Share that private URL with the intended participants; anyone who has the complete URL can request membership.
4. A teammate opens the URL, enters a display name, and receives a persistent anonymous membership for that browser.
5. Open **Room settings** to rename the room. Scale and reveal mode can be changed until tickets are added.

The UUID is intentionally unguessable and is the room's discovery secret; room data is not publicly listed. Keep the URL private. The browser session that created the room remains its facilitator, so clearing that browser's site data removes its facilitator identity. Membership and facilitator permissions still protect all room operations after discovery.

Room clients send a presence heartbeat every 15 seconds. Members are shown as disconnected after 45 seconds without a heartbeat, so abandoned browser sessions do not remain online indefinitely.

Votes are submitted through FastAPI and the response never includes the selected value. Before reveal, Supabase RLS lets a voter read only their own vote, while the browser subscribes to the separate `vote_statuses` table containing user/ticket identity and timestamps but no vote value. Raw `votes` are not part of the Realtime publication.

Manual and automatic reveal share a durable ticket-round state. Automatic mode counts members seen within the 45-second presence window and reveals atomically when the last eligible vote arrives. Re-vote clears prior values, increments the round, and clears the prior final estimate; numeric summaries and final estimates are restored after reconnect.

Facilitators can download an authorized server-side CSV containing Jira metadata, original story points, and final tickettalk estimates. Room deletion requires typing the exact room name and cascades through memberships, tickets, safe vote statuses, and private votes; the API logs only room and owner identifiers for the deletion event.

Jira imports support two room-scoped paths. A facilitator can connect their own Jira Cloud email and API token, run JQL, preview up to 500 results, and import the current issue context; or use CSV/TSV, pasted text, quoted commas, and multiline descriptions. Duplicate Jira keys require an explicit skip-or-replace choice. After pricing, the summary charts ticket ownership by final Jira assignee and highlights unassigned work. The facilitator can revise each final estimate, reassign Jira-linked tickets to Jira-assignable team members, and explicitly write the final numeric estimates and assignees back to Jira. Manual tickets remain visible as not linked to Jira. T-shirt estimates remain export-only because Jira Story Points is numeric.

Jira API tokens never reach React after submission. FastAPI validates the Jira identity, encrypts the token with `JIRA_ENCRYPTION_KEY`, and stores the ciphertext for that room. Generate a Fernet key once and place it only in the API environment:

```bash
cd backend
uv run python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

Keep this key stable while connections exist. Replacing it makes existing room credentials unreadable; disconnect/reconnect Jira before retiring an old key.

FastAPI validates the Supabase JWT and always scopes reads and writes to the authenticated actor. Creating a room and its owner membership is atomic.

## Verification

The fast unit suites use the in-memory repository. The CI database job additionally starts a clean local Supabase stack, runs every migration and pgTAP assertion, and reruns the backend suite with the real Supabase repository. That integration run enforces at least 85% backend line coverage; the frontend enforces statement, branch, function, and line thresholds in `vite.config.js`.

```bash
cd backend
uv run ruff check .
uv run pytest --cov --cov-report=term-missing

cd ../frontend
npm run lint
npm run test:coverage
npm run build
```

To reproduce the complete database gate locally, run `supabase start`, export the integration values shown by `supabase status -o env` as described by `.github/workflows/ci.yml`, and then run the backend coverage command with `--cov-fail-under=85`.

## Production configuration

Set `APP_ENV=production` and `VITE_APP_ENV=production`, provide all Supabase values and `JIRA_ENCRYPTION_KEY` from `.env.example`, configure the deployed frontend URL in `FRONTEND_ORIGIN`, and enable anonymous sign-ins in Supabase Auth. No email provider or Auth redirect URL is required. The frontend subscribes to room, membership, ticket, and vote changes through Realtime.

The production Compose topology and Coolify setup are documented in [`docs/deployment.md`](docs/deployment.md). Monitoring, incidents, restore drills, log safety, rate limits, and retention are in [`docs/operations.md`](docs/operations.md); production sign-off uses [`docs/release-checklist.md`](docs/release-checklist.md).
