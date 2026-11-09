# AdenClean

AdenClean is a home-cleaning service for Silver Spring, Maryland. This repository holds:

- the **server** (Python standard library, one process): the website, the JSON API and the admin area;
- the **mobile app** in `mobile/` (Expo, iPhone and Android);
- the **data layer**: Appwrite Cloud (TablesDB). There is no local database.

Version 1 of the app has no sign-in. A customer sends a cleaning request, checks it with a private link code kept on the phone, and leaves a review or reports an issue after the service. A marketplace (sign-in, offers, payments, vetting) also exists in the code but is switched off; see `docs/DECISIONS.md`.

## Run it locally

```bash
pip install -r requirements.txt
ADENCLEAN_STORAGE=memory SESSION_SECRET=$(python -c "import secrets; print(secrets.token_hex(32))") python main.py
```

`ADENCLEAN_STORAGE=memory` keeps everything in memory and saves nothing, which is right for local work. Without it the server expects the Appwrite settings and refuses to start if they are missing. Copy `.env.example` to see every setting; the server reads real environment variables, not the file.

## Settings

Every setting is listed with its purpose in [`.env.example`](.env.example). Secrets live only in the host's environment (Render) and are never committed.

## Appwrite setup (once, or after a schema change)

```bash
python setup_appwrite.py                    # creates the database, tables, columns and indexes; safe to re-run
python create_admin.py add you@example.com  # prompts for a 12+ character password
```

`setup_appwrite.py` needs a temporary key with database, table, column and index scopes. The running server needs only `rows.read` and `rows.write`. Tables are created with no client permissions, so only the server key can read or write customer data.

Moving data out of an old SQLite file from before the Appwrite move: `python scripts/migrate_sqlite_to_appwrite.py path/to/file.sqlite3 --dry-run`.

## Admin accounts

Each person signs in at `/admin.html` with their own email and password (salted `scrypt` hashes, 8-hour sessions). There is no shared password.

```bash
python create_admin.py add someone@example.com
python create_admin.py list
python create_admin.py disable someone@example.com   # ends their access immediately
python create_admin.py enable someone@example.com
```

## Operations

Deploying, rolling back, backups, restoring Appwrite and what to do when something breaks are in [`docs/RUNBOOK.md`](docs/RUNBOOK.md).

## Mobile app

See [`mobile/README.md`](mobile/README.md) to run, build and submit the app, and [`mobile/store/LISTING.md`](mobile/store/LISTING.md) for the store text and privacy answers.

## Known limits

- Appwrite cannot write a record and its history entry in one transaction. If the second write fails, the record is still saved and the failure is logged.
- Status changes and marketplace bookings rely on a lock inside one server process. Run a single instance.
- Rate limits are in memory and reset on restart.
- Admin lists show the newest 100 records per type.
- The app does not send emails or texts to customers; an approval is an internal decision, not a confirmed booking.
- There is no self-service deletion tool; removing a person's records is a manual step in the Appwrite console.

## Checks

```bash
python -m unittest discover -s tests        # server tests, against in-memory Appwrite tables
cd mobile && npm ci && npm run typecheck && npm run lint && npm test
```

`.github/workflows/validate.yml` runs the same checks on every push. The tests never contact the real Appwrite service.
