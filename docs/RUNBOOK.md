# AdenClean runbook

For whoever is on call. Plain steps, nothing assumed. Secrets are never pasted into chat, the repository or tickets: they go only into the Render, Appwrite and Expo dashboards.

## What runs where

| Piece | Where | Notes |
| --- | --- | --- |
| Server (website, API, admin) | Render web service `adenclean`, `https://adenclean.onrender.com` | One instance only. `render.yaml` describes it. Deploys from `main`. |
| Data | Appwrite Cloud, project `AdenClean`, NYC, database `adenclean` | Server key limited to `rows.read` and `rows.write`. |
| Mobile app | Built with EAS (Expo), shipped through App Store Connect and Google Play Console | Account `binyam4u`. |
| Errors | Render logs (JSON lines) and Sentry if `SENTRY_DSN` is set | |

## Is it up?

```bash
curl https://adenclean.onrender.com/healthz          # {"ok": true} if the process is alive
curl "https://adenclean.onrender.com/health?deep=1"  # also reads storage; 503 if Appwrite is unreachable
```

On the free plan the first request after a quiet spell takes up to a minute. That is the host waking up, not a fault. The Starter plan stays awake; it is required before store review.

## Settings

Every setting is listed in `.env.example`. Set them in Render: Service > Environment.

| Setting | Required | Notes |
| --- | --- | --- |
| `ADENCLEAN_STORAGE` | yes | `appwrite`. Never `memory` in production (the server refuses it on Render). |
| `APPWRITE_ENDPOINT`, `APPWRITE_PROJECT_ID`, `APPWRITE_API_KEY` | yes | The key needs only `rows.read` and `rows.write`. |
| `SESSION_SECRET` | yes | Render generates it. Changing it signs every admin out. |
| `ADENCLEAN_PROXY_HOPS` | yes | `1` on Render. |
| `SENTRY_DSN` | no | Turns on error reporting. |
| `PUSH_ENABLED` | no | `1` turns on request-status notifications (app 1.0.1). **Run `setup_appwrite.py` first** so the `push_tokens` column exists, or registering a phone fails. Tokens sit in that column; anyone with Appwrite console access can read them, and they are removed from backups. Leave it unset to turn notifications off at once. |
| `EXPO_ACCESS_TOKEN`, `PUSH_CA_BUNDLE` | no | Only if Expo "enhanced security" is on, or the network inspects HTTPS. |

## Deploy

1. Open a pull request. CI must be green (server tests, mobile typecheck, lint, tests and bundling).
2. Merge to `main`. Render deploys automatically (`autoDeploy: true`) and waits for `/healthz` before switching traffic.
3. Check it: `curl https://adenclean.onrender.com/health?deep=1`, then open the site and the admin page.
4. If the change added a field to the data model, run `python setup_appwrite.py` once, **before** merging, with a temporary key that has database, table, column and index scopes. It only adds what is missing and is safe to repeat. Delete the temporary key afterwards.

## Roll back

Render: Service > Events, find the last good deploy, choose **Rollback**. Takes about two minutes. If the bad change also altered data (rare), see "Restore data" below.

Git: `git revert <merge commit>` and open a pull request, so `main` matches what is running.

## Backups and restoring data

Appwrite's free plan has no automatic backups. Take one by running, on a schedule and on demand:

```bash
python export_backup.py backups/        # writes a JSON file; contains customer details, keep it private
```

On the owner's Windows PC the scheduled task `AdenClean backup` runs `scripts/backup_windows.ps1` daily at 3:00 a.m. Backups live outside the repository (`backups/` is git-ignored). Copy a recent one off the PC weekly.

Restore after a deleted table or bad data:

1. Recreate the structure: `python setup_appwrite.py` (needs the temporary setup key).
2. Load the backup rows with the Appwrite console's import, or write a short script using `store.AppwriteStore._create` for each row. Row ids are in the export, so rows keep their ids and private links keep working.
3. Admin accounts are not in backups on purpose. Recreate them: `python create_admin.py add you@example.com`.
4. Check `/health?deep=1` and open the admin page.

Moving an old SQLite file from before the Appwrite move: `python scripts/migrate_sqlite_to_appwrite.py old.sqlite3 --dry-run`, then without `--dry-run`. It skips rows already present.

## Admin accounts

```bash
python create_admin.py add someone@example.com
python create_admin.py list
python create_admin.py disable someone@example.com   # ends their access on their next request
```

A forgotten password: disable the account, add it again with a new password. Sessions last 8 hours.

## When something breaks

| Symptom | Look at | Likely cause and fix |
| --- | --- | --- |
| App says "Something went wrong on our side" | Render logs: search `"unhandled error"`; the response header `X-Request-Id` matches the log's `rid` | A bug. The log line has the error type and trace; roll back if it started after a deploy. |
| Requests fail with 500 and `/health?deep=1` returns 503 | Appwrite status page, then the key | Appwrite is down, or the key was deleted or lost its scopes. Create a new key with `rows.read` and `rows.write`, set `APPWRITE_API_KEY` in Render, redeploy. |
| Admin page says no admin accounts | `python create_admin.py list` | Data restored without admins. Add one. |
| Everyone is signed out of admin | Did `SESSION_SECRET` change? | Expected after a change. Sign in again. |
| Customers report "too many requests" | Logs: `"status": 429` and the `ip` | Rate limit (10 submissions per 15 minutes per address). Behind a shared network this can trip; wait or raise `RATE_LIMIT_MAX_REQUESTS` in `main.py`. |
| Cold-start complaints | Plan | Move to Starter. |

## Logs

One JSON object per line on stdout: `ts`, `level`, `msg`, and for requests `rid`, `method`, `path`, `status`, `ms`, `ip`. Query strings, request bodies, cookies and private link codes are never logged. Render keeps them for a limited time; search the Render Logs tab.

## Mobile releases

1. `cd mobile && npm ci && npm run typecheck && npm run lint && npm test`.
2. `npx eas-cli@latest build --platform all --profile production` (builds in the cloud; version numbers increase by themselves).
3. iOS: `npx eas-cli@latest submit --platform ios --profile production`, then press **Submit for Review** in App Store Connect.
4. Android: upload the `.aab` to a Play closed test first (personal accounts created after 2023-11-13 need 12 testers for 14 days), then apply for production.
5. Before each submission, re-read `mobile/store/LISTING.md`: the privacy answers must match the app.

Turning the marketplace on is a separate project (legal sign-offs, Stripe, Checkr, new database tables, `EXPO_PUBLIC_MARKETPLACE=1` build). See `docs/COMPLIANCE.md` and `docs/RISKS.md`.
