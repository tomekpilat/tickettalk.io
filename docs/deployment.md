# Hetzner and Coolify deployment

tickettalk runs as two containers on the existing Hetzner host. Supabase remains external and managed; this Compose project does not run a database or publish host ports.

## Topology

| Coolify service | Internal port | Public domain | Purpose |
| --- | ---: | --- | --- |
| `web` | `80` | `https://tickettalk.io` | Immutable React assets and SPA fallback |
| `api` | `8000` | `https://api.tickettalk.io` | FastAPI application |

Both services share only the private Compose `app` network. Coolify terminates TLS and routes each domain to its internal service port.

## Create the Coolify application

1. In the existing Coolify project, create a **Docker Compose** resource from `tomekpilat/tickettalk.io`.
2. Set the production branch to `main` and the Compose file to `/compose.yaml`.
3. Add `https://tickettalk.io` to `web`, selecting container port `80`.
4. Add `https://api.tickettalk.io` to `api`, selecting container port `8000`. Do not add `:8000` to the public URL and do not publish host ports.
5. Enable HTTPS redirect and certificate management in Coolify.
6. Configure deployment-failure and unhealthy-service notifications using the provider already used by the other applications on this server.

## Variables

Set these as Coolify build variables for `web`:

```dotenv
VITE_API_URL=https://api.tickettalk.io
VITE_SUPABASE_URL=https://YOUR_PROJECT.supabase.co
VITE_SUPABASE_ANON_KEY=YOUR_PUBLISHABLE_ANON_KEY
```

Set these as runtime variables for `api`; mark the service-role key as secret and never expose it to `web`:

```dotenv
APP_ENV=production
FRONTEND_ORIGIN=https://tickettalk.io
SUPABASE_URL=https://YOUR_PROJECT.supabase.co
SUPABASE_SERVICE_ROLE_KEY=YOUR_SERVICE_ROLE_KEY
JIRA_ENCRYPTION_KEY=YOUR_FERNET_KEY
JIRA_OAUTH_CLIENT_ID=YOUR_ATLASSIAN_CLIENT_ID
JIRA_OAUTH_CLIENT_SECRET=YOUR_ATLASSIAN_CLIENT_SECRET
JIRA_OAUTH_REDIRECT_URI=https://tickettalk.io/jira/oauth/callback
RATE_LIMIT_JOIN_PER_MINUTE=20
RATE_LIMIT_IMPORT_PER_MINUTE=12
RATE_LIMIT_VOTE_PER_MINUTE=120
```

Compose uses required-variable expressions, so a build with an incomplete environment stops before deployment. In Supabase Auth, enable anonymous sign-ins; email providers and redirect allow-list entries are not required. Apply all migrations in `supabase/migrations` before inviting users.

Generate `JIRA_ENCRYPTION_KEY` once with the command documented in the root README. It encrypts per-room OAuth access/refresh tokens and fallback API tokens and must exist only in the API runtime. Keep it stable across deploys and backups. Rotating it requires every active Jira room connection to be recreated unless a key-rotation migration is implemented first.

## Configure Atlassian OAuth 2.0 (3LO)

1. In the Atlassian developer console, create one OAuth 2.0 (3LO) integration for tickettalk. Configure it for sharing/distribution; otherwise only the app owner can authorize it.
2. Add the Jira API classic scopes `read:jira-work`, `read:jira-user`, and `write:jira-work`. Tickettalk requests `offline_access` during consent so it can rotate refresh tokens.
3. Add the callback URL `https://tickettalk.io/jira/oauth/callback`. Atlassian requires an exact match, including scheme, host, path, and trailing slash behavior.
4. Copy the client ID and secret into the API-only Coolify variables above. Never add the client secret to the frontend build variables.
5. Redeploy the API and web services. In a disposable room, enter the intended `*.atlassian.net` site, choose **Continue with Atlassian**, approve that site, and verify import plus write-back.

Atlassian permits one exact callback URL per 3LO app. For local development, create a separate non-shared OAuth app with `http://localhost:5173/jira/oauth/callback`, and use its client ID, client secret, and callback in the local API environment. Do not reuse the production app or production client secret locally. Tickettalk matches the site typed before consent against Atlassian's accessible resources, which prevents silently connecting a different Jira tenant when an account can access several sites.

## First deployment checks

1. Deploy and wait for both Coolify health checks to become green.
2. Confirm `https://tickettalk.io/healthz` returns `200`, `https://api.tickettalk.io/health` returns `{"status":"ok"}`, and `https://api.tickettalk.io/health/ready` returns `{"status":"ready"}`.
3. Without registering, create a room, copy its UUID URL, open that exact URL in a private browser, join, vote, reveal, and export. Confirm that a different UUID returns an unavailable-room response.
4. In a test room, connect with Atlassian OAuth, preview a narrow JQL query, import one issue, refresh the page, and write its final result back. Also verify the advanced API-token fallback once, then disconnect the room.
5. Inspect the built web assets and browser network log: `SUPABASE_SERVICE_ROLE_KEY`, `JIRA_ENCRYPTION_KEY`, `JIRA_OAUTH_CLIENT_SECRET`, OAuth tokens, and Jira API tokens must not appear anywhere.
6. Confirm cross-origin API calls originate only from `https://tickettalk.io` and produce no mixed-content errors.

## Deploy and rollback

- Normal deploy: merge only after CI succeeds; Coolify auto-deploys `main`.
- Rollback: in Coolify deployments, select the last known-good deployment and choose **Redeploy**. Verify both health endpoints and the room smoke test before closing the incident.
- If a migration is forward-only, roll the application forward with a correcting migration instead of reverting the database blindly.
- Keep at least the previous successful application image/deployment available until the new release has passed the smoke test.

## Secret rotation

1. Generate or rotate the key in Supabase.
2. Replace the matching Coolify variable. The service-role key belongs only to `api`; the publishable anon key belongs only to the `web` build.
3. Redeploy the affected service and complete the health and room smoke tests.
4. Revoke the old key after the new deployment is healthy. Never paste keys into an issue, commit, build log, or support message.

## Backups and ownership

- Monitor database backups and point-in-time recovery in the Supabase project; the available retention depends on the selected Supabase plan.
- Coolify configuration and server backups are monitored with the existing Hetzner/Coolify process used by the other hosted applications.
- Exported room CSV files are user-managed artifacts, not database backups.
- Record the date, operator, source backup, target project, and verification result for every restore drill.

Monitoring, incident response, tested-restore expectations, log safety, rate limits, and retention are defined in [`operations.md`](operations.md). Use [`release-checklist.md`](release-checklist.md) for production sign-off.
