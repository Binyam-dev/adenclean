# MVP backlog

Severity: **P0** blocks launch, **P1** hurts the user or fails an exit criterion, **P2** polish.
Status: open, done (with the commit), BLOCKED (with evidence), or HUMAN (needs the owner).
Audit cycle 1 ran on 2026-11-09 against `main` at a1fe903.

## Audit cycle 1: what was run

| Check | Result |
| --- | --- |
| Python tests (`python -m unittest discover -s tests`) | see cycle notes below |
| Mobile typecheck (`npm run typecheck`) | pass |
| Mobile tests (`npm test`) | 57 pass |
| Mobile lint (`npx eslint src`) | 7 errors, 1 warning |
| `npx expo-doctor` | 19/20; 7 packages behind the SDK 58 patch versions |
| Live `/healthz` | `{"ok": true}` |

## Facts in the brief that are stale

- The app is no longer "v1 only". A marketplace (sign-in, offers, payments, vetting, report and block) was built and merged behind `MARKETPLACE_ENABLED` (server) and `EXPO_PUBLIC_MARKETPLACE` (app). Both are off. v1 for the stores is still the three no-sign-in customer flows. See DECISIONS.md.
- Admin accounts are already individual (scrypt hashes, 8-hour signed sessions). No shared password exists in code or config.
- Private links are already 256-bit random tokens, stored only as SHA-256 hashes.
- Render is still on the free plan (first request after sleep took 32 s on 2026-11-07).

## Open items

| # | Sev | Area | Item | Status |
| --- | --- | --- | --- | --- |
| 1 | P0 | A | SQLite is still a runtime backend (`SqliteStore`, `SqliteTables`, default `ADENCLEAN_STORAGE=sqlite`). The exit criteria say no SQLite. A typo in the env var would silently write customer data to a local file on an ephemeral disk. | open |
| 2 | P0 | A | Replit leftovers: `.replit`, `.replitignore`, `.agents/memory/` (Replit agent notes), README wording. | open |
| 3 | P1 | A | No `.env.example`; env vars are documented only in prose. | open |
| 4 | P1 | A | No migration script for data in an old SQLite file. | open |
| 5 | P1 | B | An unexpected exception in a handler drops the connection with no JSON body, and is logged as an unstructured traceback. Errors must be consistent. | open |
| 6 | P1 | B | No `/health` endpoint that checks storage; `/healthz` only proves the process is up. | open |
| 7 | P1 | B/D | Cold start: the app times out after 15 s and does not retry. The free plan wakes in about 30 s, so the first request of the day fails. | open |
| 8 | P1 | C | Admin cannot assign a request to a cleaner. | open |
| 9 | P1 | D | Lint fails (7 errors), so "lint passes from a fresh clone" is false. CI does not run lint. | open |
| 10 | P1 | D | Expo doctor: 7 packages behind the SDK 58 versions. | open |
| 11 | P1 | D | Marketplace screens (sign-in, jobs, cleaner, blocked) are reachable by deep link in a v1 build even though the tab is hidden. | open |
| 12 | P1 | F | No error monitoring; server logs are unstructured and log the proxy address, not the client. | open |
| 13 | P1 | F | No RUNBOOK (deploy, rollback, env vars, Appwrite recovery). | open |
| 14 | P1 | G | Security headers: no Content-Security-Policy, frame protection or Permissions-Policy. | open |
| 15 | P1 | G | Secrets scan of full git history and dependency audit. | open (agent running) |
| 16 | P1 | E | Store pack must be re-checked against current Apple and Google rules, and against what the app collects now. | open (agent running) |
| 17 | P1 | H | Marketplace tables (`reports`, `blocks`, etc.) are not in production Appwrite. Not needed for v1 (flag off). | HUMAN (run `setup_appwrite.py` only when enabling the marketplace) |
| 18 | P0 | H | Render is on the free plan: it sleeps, and store reviewers will hit a 30-second first load. | HUMAN (billing) |
| 19 | P1 | D | iOS build 7 predates four merged app changes. A new production build is needed for both stores. | open |
| 20 | P2 | A | `store.py` is 784 lines (limit 500). Removing SQLite fixes this. | open |
| 21 | P2 | web | `hallmark-redesign` branch (website redesign) is local only, hotlinks a Wikimedia photo and preloads TTF fonts. Not part of the app MVP. | parked: BACKLOG_POST_MVP.md |
| 22 | P2 | D | `validation.ts` has an unused eslint-disable directive. | open |

Items are appended as later audit cycles find them.
