# MVP release checklist

## Automated release gate

- [x] Backend formatting/lint and API tests run in CI.
- [x] Frontend lint, component tests, and production build run in CI.
- [x] Every migration is applied to a clean local Supabase stack in CI.
- [x] pgTAP exercises facilitator, member, anonymous, and cross-room RLS boundaries in CI.
- [x] The credentialed two-client flow creates, imports, joins, activates, votes, reveals, saves, exports, and deletes a room in CI.
- [x] Concurrent auto-votes and duplicate manual reveal are covered.
- [x] Production Compose configuration and both images build in CI.
- [x] Request logs are structured and tested not to expose authorization tokens.
- [x] Rate-limit and dependency-readiness behavior is covered by API tests.
- [x] Jira OAuth state/callback/refresh, advanced API-token credentials, JQL import, assignee selection, write-back, RLS denial, and room-deletion cascade are covered by automated tests.

Configure GitHub branch protection for `main` to require all four CI jobs and an approving review. Configure Coolify to deploy only `main`; never use an unprotected feature branch as the production source.

## Product and accessibility review

- [x] Facilitator and member roles are represented by separate authenticated clients in the integration flow.
- [x] Unrevealed vote values are absent from API receipts, shared vote status, and Realtime publication.
- [x] Interactive controls have visible keyboard focus; dialogs have accessible names; asynchronous status is announced.
- [x] Layouts include tablet and phone breakpoints down to the supported 320 px viewport.
- [x] Motion is suppressed when the browser requests reduced motion.
- [x] Instrument Sans and JetBrains Mono are bundled into the production build instead of depending on locally installed fonts.
- [x] Creating and joining rooms requires only a display name; no email, password, or registration screen is present.
- [x] Room discovery requires the complete random UUID URL, while membership and facilitator permissions continue to protect room operations.

## Production operator sign-off

Complete this section for the actual release; record evidence in the deployment ticket.

- [ ] Production Supabase migrations applied and anonymous Auth enabled.
- [ ] Coolify domains, TLS, secrets, resource limits, and health checks verified.
- [ ] Atlassian 3LO app is shared, exact callback and scopes are configured, and OAuth consent succeeds for a non-owner Atlassian account.
- [ ] External web, API liveness, and Supabase readiness monitors alert the on-call channel and recovery notifications arrive.
- [ ] Backup retention is recorded and an isolated restore drill has a successful date/result.
- [ ] Desktop and phone smoke tests cover create, share, join, CSV and Jira import, select, two votes, reveal, estimate, summary ownership distribution, reassignment, price editing, Jira write-back, export, and exact-name delete.
- [ ] Privacy copy states active-room retention, deletion behavior, and backup expiry.
- [ ] Rollback owner, incident contact, and release SHA are recorded.

Release operator: ____________________  Date: __________  SHA: ____________________
