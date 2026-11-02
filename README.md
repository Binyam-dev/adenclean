# AdenClean

AdenClean is a home-cleaning service preview for Silver Spring, Maryland: customer inquiries, cleaner availability submissions, private customer feedback links, and a private admin review area with individual admin accounts.

## Run it locally

```bash
pip install -r requirements.txt
python main.py          # serves on port 5000
```

Without any settings the app stores data in a local SQLite file (`data/adenclean.sqlite3`) and prints a warning. That mode is for development and tests only. Do not collect real customer or cleaner information with it.

## Production storage: Appwrite

Production data lives in [Appwrite](https://appwrite.io) (TablesDB). Set these as secrets in the host (never commit them):

| Setting | Value |
| --- | --- |
| `ADENCLEAN_STORAGE` | `appwrite` (the app refuses to start if the settings below are missing) |
| `APPWRITE_ENDPOINT` | e.g. `https://nyc.cloud.appwrite.io/v1` |
| `APPWRITE_PROJECT_ID` | your Appwrite project ID |
| `APPWRITE_API_KEY` | server API key with database, table, column, index and row scopes |
| `APPWRITE_DATABASE_ID` | optional, defaults to `adenclean` |
| `SESSION_SECRET` | long random string used to sign admin sessions |

One-time setup:

```bash
python setup_appwrite.py                    # creates the database, tables, columns and indexes
python create_admin.py add you@example.com  # prompts for a 12+ character password
```

Tables are created with no client permissions, so only the server API key can read or write customer data. Keep that key out of the browser, the repository and chat.

## Admin accounts

Each person signs in at `/admin.html` with their own email and password (stored as salted `scrypt` hashes). There is no shared password.

```bash
python create_admin.py add someone@example.com
python create_admin.py list
python create_admin.py disable someone@example.com   # ends their access immediately
python create_admin.py enable someone@example.com
```

Status changes in the review history record the admin's email.

## Backups

Appwrite's free plan does not include automatic backups. Run `python export_backup.py [folder]` on a schedule and copy the file somewhere other than the machine running the app. Exports contain customer and cleaner details (admin password hashes are left out), so store them privately and delete old copies. `backups/` is git-ignored.

## Deploy the server (Render)

`render.yaml` describes an always-on Render web service. In Render choose New > Blueprint,
pick this repository, and paste `APPWRITE_API_KEY` (the runtime key with only `rows.read`
and `rows.write`) when asked. `SESSION_SECRET` is generated for you. The service sets
`ADENCLEAN_PROXY_HOPS=1` so rate limits count each visitor separately behind Render's
proxy, and answers `/healthz` for health checks. Then use the service's `https://` address as
`EXPO_PUBLIC_API_URL` for the mobile app (see `mobile/README.md`).

## Mobile app

The iPhone and Android app lives in `mobile/` (Expo). See `mobile/README.md` to run it, build
it, and submit it to the App Store and Google Play.

## Known limits

- Appwrite cannot write a record and its history entry in one transaction. If the second write fails, the record is still saved and the failure is logged.
- Status changes use a lock inside one app process. Run a single instance; several instances could in rare cases overwrite each other's status change.
- Rate limits are in memory and reset on restart.
- Admin lists show the newest 100 records per type.
- The app does not send emails or texts; approval is an internal decision, not a confirmed booking.

## Privacy and beta access

Before real customer data: confirm retention and deletion procedures, keep test submissions out of launch data, and keep the Replit deployment on **Sharing → Invite only** until access controls and support are ready. There is no self-service deletion tool yet; removing a person's records is a manual step in the Appwrite console.

## Checks

`.github/workflows/validate.yml` runs Python, JavaScript and test checks on every push (`python -m unittest discover -s tests -v`). The tests run the whole app against both the local SQLite store and an in-memory stand-in for Appwrite. They do not contact the real Appwrite service.
