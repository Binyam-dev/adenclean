# MVP backlog

Severity: **P0** blocks launch, **P1** hurts the user or fails an exit criterion, **P2** polish.
Status: open, done (with the commit), BLOCKED (with evidence), or HUMAN (needs the owner).

## Audit cycles

| Cycle | Date | Result |
| --- | --- | --- |
| 1 | 2026-11-09 | Python tests passed; mobile typecheck passed; mobile tests 57 pass; lint 7 errors and 1 warning; expo-doctor 19 of 20; live `/healthz` ok. 22 items found. |
| 2 | 2026-11-09 | After the fixes below: Python 177 tests pass; mobile typecheck passes, lint 0 errors 0 warnings, 67 tests pass; expo-doctor 20 of 20; Android and iOS bundles build; live customer flows pass against live Appwrite; local admin flow passes. Two more items found and fixed during the cycle (13 and 14 in the "found later" list). No new P0 or P1 open. |

The re-audit after the last batch of P0 and P1 fixes is cycle 2. Two cycles of the 15 allowed were used.

## Facts in the brief that are stale

- The app is no longer "v1 only". A marketplace (sign-in, offers, payments, vetting, report and block) was built and merged behind `MARKETPLACE_ENABLED` (server) and `EXPO_PUBLIC_MARKETPLACE` (app). Both are off. Version 1 for the stores is the three no-sign-in customer flows. See DECISIONS.md.
- Admin accounts were already individual (scrypt hashes, 8-hour signed sessions). No shared password exists in code or config.
- Private links were already 256-bit random tokens stored only as SHA-256 hashes.
- Render is still on the free plan.

## Items

| # | Sev | Area | Item | Status |
| --- | --- | --- | --- | --- |
| 1 | P0 | A | SQLite was a runtime backend and the default. | done (c259100) |
| 2 | P0 | A | Replit files (`.replit`, `.replitignore`, `.agents/`) and README wording. | done (c259100) |
| 3 | P1 | A | No `.env.example`. | done (afa1119) |
| 4 | P1 | A | No migration script for an old SQLite file. | done (afa1119) |
| 5 | P1 | B | An unexpected exception dropped the connection with no JSON body. | done (2f21dd4) |
| 6 | P1 | B | No `/health` that checks storage. | done (2f21dd4) |
| 7 | P1 | B/D | Cold start: the app gave up after 15 s with no retry or message. | done (da88d6c) |
| 8 | P1 | C | Admin could not assign a request. | done (46ed9c3) |
| 9 | P1 | D | Lint failed (7 errors); CI did not run lint. | done (7ce6083, da88d6c) |
| 10 | P1 | D | 7 Expo packages behind SDK 58. | done (7ce6083) |
| 11 | P1 | D | Marketplace screens reachable by link in a version 1 build. | done (da88d6c) |
| 12 | P1 | F | No error monitoring; unstructured logs. | done (2f21dd4); Sentry turns on when `SENTRY_DSN` is set |
| 13 | P1 | F | No runbook. | done (c99ef64) |
| 14 | P1 | G | No CSP, frame protection or Permissions-Policy. | done (2f21dd4) |
| 15 | P1 | G | Secrets scan of history and dependency audit. | done: no real secret; see SECURITY_REVIEW.md |
| 16 | P1 | E | Store pack checked against current Apple and Google rules. | done: STORE_REQUIREMENTS.md, LISTING.md, `ios.privacyManifests` |
| 17 | P1 | H | Marketplace tables are not in production Appwrite. | not needed for version 1 (flag off); HUMAN when enabling |
| 18 | P0 | H | Render is on the free plan (sleeps; a reviewer waits up to a minute). | HUMAN: approve Starter ($7/month) |
| 19 | P1 | D | iOS build 7 predates four merged app changes. | builds queued on EAS (see READY_REPORT.md) |
| 20 | P2 | A | `store.py` was 784 lines. | done: 411 lines |
| 21 | P2 | web | `hallmark-redesign` website branch not merged. | parked (BACKLOG_POST_MVP.md) |
| 22 | P2 | D | Unused eslint directive. | done (7ce6083) |

### Found later (cycle 1 to 2)

| # | Sev | Area | Item | Status |
| --- | --- | --- | --- | --- |
| 23 | P1 | G | The static file handler listed any folder's contents. | done (c99ef64) |
| 24 | P1 | E | Stripe's payment SDK was in the version 1 binary although the privacy answers say no payments. | done (da88d6c); verified with a control |
| 25 | P2 | G | Python dependencies are ranges, not hashes. | open (BACKLOG_POST_MVP.md) |
| 26 | P2 | G | 15 moderate npm advisories in Expo build tools (not in the app). | accepted; revisit on the next Expo patch |

## Human gates (not code)

See READY_REPORT.md for the exact steps and values.

1. Merge the pull request so Render deploys it (nothing is merged without the owner).
2. Render: Starter plan; check the environment settings.
3. Admin end-to-end against production (needs an admin login, which only the owner has).
4. Apple: attach the new build, upload screenshots, answer the privacy and age questions, press Submit for Review.
5. Google Play: identity verification, closed test with 12 testers for 14 days, Data safety form, then production access.
