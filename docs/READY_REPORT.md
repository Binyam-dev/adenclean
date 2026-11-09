# Ready report: AdenClean version 1

Date: 2026-11-09. Branch `mvp-readiness` (pull request, not merged). Findings and status for each item: `docs/MVP_BACKLOG.md`.

## Verdict

Everything that can be done in code is done and verified. Version 1 cannot go live from here for four reasons that are the owner's to resolve (merge, Render plan, an admin login for the production check, and the Apple and Google console steps). Exact steps are at the end.

Scope reminder: version 1 is the three customer flows with no sign-in. A marketplace also exists in the code but is switched off and is not part of this release (see `docs/DECISIONS.md`).

## Exit criteria

| # | Criterion | Status | Evidence |
| --- | --- | --- | --- |
| 1 | Zero open P0 or P1 items; P2 listed | **Met in code; two P0 and P1 items are owner actions** | `docs/MVP_BACKLOG.md`. Open P0/P1: Render Starter plan (billing), merge to deploy. P2 listed. |
| 2 | Clean install, typecheck, lint and all tests pass from a fresh clone | **Met** | Cloned `mvp-readiness` from GitHub at `531412c` into a new folder with a new virtualenv. Server: `Ran 179 tests ... OK`. Mobile: `npm ci` (818 packages), typecheck exit 0, lint exit 0 (0 errors, 0 warnings), `# tests 67 # pass 67 # fail 0`. CI runs the same, plus lint, JS syntax and Android and iOS bundling. |
| 3 | Three customer flows and the admin flow work end to end against the deployed server and live Appwrite | **Customer flows met on production; admin flow met locally, not on production** | See "End-to-end runs". The admin flow on production needs an admin login, which only the owner has. |
| 4 | EAS production builds for iOS and Android complete | **iOS met; Android see below** | iOS build 8 finished. Android build 3: see "EAS builds". |
| 5 | No secrets in the repo or history; no SQLite, Supabase or Replit leftovers | **Met** | Scan of 57 commits, all branches, plus unreachable objects: no real secret (`docs/SECURITY_REVIEW.md`). This branch's added lines: 0 secret-pattern hits. Supabase: 0 references. Replit: files removed. SQLite: backend removed; the words remain only in the migration script and its test, a test that asserts the backend is gone, and one README line pointing at the script. A test fails if they appear anywhere else. |
| 6 | Store checklist complete, every asset and answer ready to paste | **Met** | `mobile/store/LISTING.md` (all text, privacy and Data safety answers, review notes), `docs/STORE_REQUIREMENTS.md` (current rules with sources), screenshots in `mobile/store/screenshots/` (iPhone 1206x2622 and 1320x2868, Android 1080x2160), icon and feature graphic in `mobile/store/`. |

## End-to-end runs

Local, with an admin account, in-memory Appwrite tables (`scripts/smoke_test.py`; the same steps run as a test on every CI run):

```
PASS  health check answers  (HTTP 200)
PASS  deep health check reads storage  (HTTP 200)
PASS  flow 1: a request is saved  (HTTP 201)
PASS  bad input is refused  (HTTP 400)
PASS  a wrong private code is refused  (HTTP 404)
PASS  flow 2: the request is found by its private code  (HTTP 200, status pending)
PASS  a review before the service is complete is refused  (HTTP 409)
PASS  admin: sign in  (HTTP 200)
PASS  admin: the request is in the list  (HTTP 200)
PASS  admin: assign the request  (HTTP 200)
PASS  admin: approve
PASS  admin: mark complete
PASS  the customer now sees it as complete
PASS  flow 3: a review is saved  (HTTP 201)
PASS  a second review is refused  (HTTP 409)
PASS  flow 3: an issue report is saved  (HTTP 201)
PASS  admin: the review is listed  (HTTP 200)
PASS  admin: moderate the review
PASS  admin: the issue is listed  (HTTP 200)
PASS  admin: moderate the issue
PASS  admin: sign out
ALL STEPS PASSED
```

Production (`https://adenclean.onrender.com`, live Appwrite), customer flows only:

```
$ python scripts/smoke_test.py https://adenclean.onrender.com
PASS  health check answers  (HTTP 200)
SKIP  deep health check (this server is older than the /health endpoint)
PASS  flow 1: a request is saved  (HTTP 201)
PASS  bad input is refused  (HTTP 400)
PASS  a wrong private code is refused  (HTTP 404)
PASS  flow 2: the request is found by its private code  (HTTP 200, status pending)
PASS  a review before the service is complete is refused  (HTTP 409)
NOTE  no admin login given: request E3117D07D547 stays pending. Cancel it in the admin page.
ALL STEPS PASSED
```

Not yet run on production: the review and issue steps (they need a completed request, which needs an admin), and the deep health check (the deployed server predates this branch). After the merge, run:

```bash
ADMIN_EMAIL=you@example.com ADMIN_PASSWORD='your password' python scripts/smoke_test.py https://adenclean.onrender.com
```

It writes one more test request named "SMOKE TEST - ignore". Cancel both test requests in the admin page afterwards (references `E3117D07D547` and the new one).

## What changed (by workstream)

- **A Data layer:** SQLite and Replit removed; Appwrite only (`memory` mode for local work, refused on Render); `.env.example`; re-runnable migration script; `setup_appwrite.py` adds the new column.
- **B API server:** any crash returns one JSON error with a request id, is logged and reported; structured logs; `/health` and `/health?deep=1`; folder listing off; CSP and frame and permission headers (checked in a browser, no violations); the app retries status checks and waits for a sleeping server without ever repeating a send.
- **C Admin:** individual accounts already existed (scrypt, 8-hour sessions); admin can now assign a request. Not on production until merged.
- **D App:** lint clean; Expo doctor 20 of 20; waking-up notice (screenshot `docs/evidence/waking-up-notice.jpg`); marketplace screens and the payment SDK are absent from version 1 builds (verified with Expo's autolinking report, with a control); privacy manifest; every text and background colour pair is at least 4.67:1 (WCAG AA needs 4.5); text size follows the system setting; labels on interactive elements.
- **E Store:** requirements checked against the official Apple, Google and Expo pages today (`docs/STORE_REQUIREMENTS.md`). Items those pages do not settle are marked unverified and handled conservatively.
- **F Reliability:** Sentry on the server (off until `SENTRY_DSN` is set), JSON logs, `docs/RUNBOOK.md`.
- **G Security:** history scan, dependency audits, endpoint review (`docs/SECURITY_REVIEW.md`). One real finding fixed (folder listing).
- **H Deployment:** `render.yaml` already deploys from `main` with a health check and `starter` plan. The live service is still on the free plan.

## EAS builds

| Platform | Build | Result |
| --- | --- | --- |
| iOS production | 8 | FINISHED. https://expo.dev/accounts/binyam4u/projects/adenclean/builds/0c57765f-85bd-4b18-a8d8-2f481938fd4b |
| Android production | 3 | ANDROID_STATUS_PLACEHOLDER https://expo.dev/accounts/binyam4u/projects/adenclean/builds/e0df3cce-73a6-49b8-98a0-3ffe4d483193 |

Credentials for both already existed on EAS, so nothing stopped at the credential step.

## BLOCKED

Nothing is blocked by a technical problem. The items below wait on the owner.

## Human steps left, in order

1. **Merge the pull request** for branch `mvp-readiness`. Render deploys by itself in about two minutes. Then check: `curl "https://adenclean.onrender.com/health?deep=1"` should return `{"ok": true, "storage": "appwrite", ..., "database": "ok"}`.
2. **Run `python setup_appwrite.py` once before or right after the merge**, with a temporary Appwrite key (scopes: databases, tables, columns, indexes, rows) in `APPWRITE_ENDPOINT`, `APPWRITE_PROJECT_ID` and `APPWRITE_API_KEY`. It adds the `assigned_to` column (and the marketplace tables, which stay unused). Delete the temporary key afterwards. Until you do, assigning a request in the admin page will fail; nothing else is affected.
3. **Render > Billing: choose the Starter plan ($7 a month).** Without it the first request after a quiet spell takes up to a minute, which will frustrate store reviewers and customers. Also confirm in Render > Environment: `ADENCLEAN_STORAGE=appwrite`, `ADENCLEAN_PROXY_HOPS=1`, `APPWRITE_ENDPOINT=https://nyc.cloud.appwrite.io/v1`, `APPWRITE_PROJECT_ID=6ae7b1ed0005ab702dc9`, and that `APPWRITE_API_KEY` is the runtime key with only `rows.read` and `rows.write`. Optional: `SENTRY_DSN` from a free Sentry project, to get error alerts.
4. **Production admin check:** run the smoke test above with your admin login, then cancel the two test requests.
5. **Apple (App Store Connect, app 6830724671):** `cd mobile && npx eas-cli@latest submit --platform ios --profile production` (or attach build 8 in the TestFlight tab), choose build 8 on version 1.0, upload both screenshot sets from `mobile/store/screenshots/ios-6.3/` and `ios-6.9/`, paste the text from `mobile/store/LISTING.md`, answer the App Privacy questions from the table in that file, answer the age-rating questionnaire "None" throughout (result 4+), paste the App Review notes (the demo request `E530B601923D` must stay in place; the link is in `%LOCALAPPDATA%\AdenClean\apple-review-demo-link.txt`), then press **Submit for Review**.
6. **Google Play:** finish identity verification in Play Console (trader status, an Android device sign-in, phone verification). Create the app, upload the Android build 3 `.aab` to a **closed test**, recruit more than 12 testers and keep them opted in for 14 days (personal accounts created after 2023-11-13), then apply for production access. Fill in Data safety and the content rating from `LISTING.md`. Check the 16 KB page-size status in the console after upload.
7. **Search:** verify the site in Google Search Console and submit `https://adenclean.onrender.com/sitemap.xml`.

## Risks and limits to know about

- The 16 KB page-size compatibility of every native library in Expo SDK 58 is unverified (Google requires it for updates from 2027-02-01). The Play Console shows the status.
- Whether a typed town or ZIP counts as "location" in the Apple and Google forms is unverified; it is declared as coarse location to be safe.
- Apple's screenshot page contradicts itself about which iPhone size is mandatory, so both sets are supplied.
- The admin flow and the new assignment field have not run against production Appwrite.
- One server instance only (a documented limit); rate limits reset on restart.
- 15 moderate npm advisories sit in Expo's build and lint tools, not in the app. No fix exists that does not downgrade Expo.
- Customer requests are kept until deleted by hand, as the privacy policy says.
