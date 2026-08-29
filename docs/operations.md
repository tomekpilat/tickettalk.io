# Production operations

This runbook covers the first response for the Coolify application and managed Supabase project. It complements the deployment steps in [`deployment.md`](deployment.md).

## Monitoring and alerting

Configure an external uptime monitor to check these endpoints every minute from outside Hetzner:

| Check | Expected result | Meaning |
| --- | --- | --- |
| `https://tickettalk.io/healthz` | HTTP `200`, body `ok` | DNS, TLS, Coolify routing, nginx, and web container are available |
| `https://api.tickettalk.io/health` | HTTP `200`, JSON status `ok` | API process is available |
| `https://api.tickettalk.io/health/ready` | HTTP `200`, JSON status `ready` | API can query Supabase |

Notify the existing on-call channel after two consecutive failures and again on recovery. In Coolify, enable deployment-failed and unhealthy-container notifications for both services. Enable Supabase incident notifications for the production project. The readiness check must not replace the API container liveness check: a temporary Supabase outage should alert operators without creating an API restart loop.

## Logs and incident correlation

FastAPI emits one JSON line per request with `event`, `request_id`, method, path, status, and duration. The API accepts a valid `X-Request-ID` from the proxy and returns it to the browser; otherwise it creates one. Event logs use the same JSON format.

Never add authorization headers, cookies, request/response bodies, Supabase keys, or unrevealed vote values to logs. When investigating a report, ask for the response `X-Request-ID`, time, and room URL—not the user's token. Search Coolify logs by request ID, then correlate with Supabase logs by time and route.

## Rate-limit response

Join, Jira import/preview, and vote writes are limited independently per bearer identity (or hashed client address before authentication). Defaults are 20 joins, 12 import requests, and 120 vote writes per minute. A limited request receives `429`, `Retry-After`, and `X-RateLimit-Limit`.

If legitimate traffic is limited, confirm the route and caller first. Adjust `RATE_LIMIT_JOIN_PER_MINUTE`, `RATE_LIMIT_IMPORT_PER_MINUTE`, or `RATE_LIMIT_VOTE_PER_MINUTE` in Coolify and redeploy. Do not disable all limits during an attack; block the source at the proxy and rotate exposed credentials.

## Incident triage

1. Acknowledge the alert and record the start time, affected checks, current deployment SHA, and operator.
2. Check Coolify service health and deployment logs. Use a request ID to inspect API logs without collecting credentials.
3. Check the Supabase project health and provider status. If liveness is healthy but readiness is not, leave the API running while investigating Supabase.
4. For a release regression, redeploy the last known-good Coolify deployment. Do not reverse a production migration blindly.
5. Run the create/join/two-vote/reveal/export smoke test after recovery.
6. Record impact, root cause, mitigation, follow-up owner, and whether any key or personal data may have been exposed.

## Backup and restore drill

Supabase database backups are the system backups. CSV exports are user artifacts and are not sufficient for recovery. Confirm the production plan's backup retention and point-in-time recovery window in the Supabase dashboard at every release.

Test restoration quarterly and before a destructive schema migration:

1. Create an isolated, access-restricted Supabase recovery project. Never restore over production for a drill.
2. Select a production backup or point in time, record its timestamp and identifier, and restore it using the Supabase-supported process for the active plan.
3. Point a temporary API deployment at the recovery project with newly issued recovery-only keys.
4. Verify room, membership, ticket, vote-status, private vote, reveal-round, final-estimate, and cascade relationships. Run the API two-client flow and the pgTAP RLS suite.
5. Delete the temporary API, revoke its keys, and remove the recovery project according to the approved data-handling process.
6. Record recovery point achieved, recovery time, verification results, operator, and follow-ups in the operations log.

## Retention and deletion

Room data is retained until its facilitator deletes the room. Deletion is immediate at the application layer and cascades to memberships, tickets, vote statuses, and votes; provider backups may retain a recoverable copy until the configured backup window expires. Document that window in the privacy notice before launch. Do not promise deletion from immutable backups sooner than the Supabase plan provides.

Application logs should be retained for 30 days unless an incident or legal requirement needs a documented hold. Logs must contain identifiers and operational metadata only, never credentials or vote values. Review access to Coolify, Hetzner, Supabase, DNS, and the uptime provider quarterly and when a team member leaves.

## Secret rotation and rollback

Use the deployment runbook for normal deploys, rollback, and key rotation. After any rotation, verify liveness, readiness, registration-free room creation, anonymous join through the exact UUID URL, Realtime updates, and export before revoking the old key. A Supabase service-role key must exist only in the API service runtime environment.
