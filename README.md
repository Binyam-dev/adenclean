# AdenClean

AdenClean is a home-cleaning service preview with customer inquiries, cleaner availability submissions, and a private admin review area.

## Run the app

The app uses Python's standard library and serves on port `5000`.

```bash
python main.py
```

In Replit, start the **Start application** workflow to open the preview.

## Required Replit Secrets

Add these in Replit Secrets; never commit their values:

- `ADENCLEAN_ADMIN_PASSWORD` — at least 12 characters.
- `SESSION_SECRET` — a long, random secret used to sign admin sessions.

The admin area is at `/admin.html`. It uses one shared password, not individual staff accounts.

## Preview data and privacy

Customer requests, cleaner availability, reviews, and service issues are stored in the local SQLite database at `data/adenclean.sqlite3`. The `data/` directory is excluded from Git and Replit uploads.

This storage is for preview use, not a durable production database. Before collecting real customer or cleaner information, choose durable storage and backups, define retention and deletion procedures, and replace shared-password access with individual accounts and roles. Keep test submissions out of launch data.

## Private beta

For a restricted beta, publish from Replit with **Sharing → Invite only** and invite only the intended testers. Visitors to a private deployment must sign in through Replit. Publishing and managing the invite list are Replit workspace actions; this repository does not set deployment visibility.

Do not switch the deployment to public until access controls, data storage, privacy terms, and operational support are ready.

## GitHub checks

The workflow in `.github/workflows/validate.yml` runs Python, JavaScript, and static-link checks on pushes and pull requests. Keep the GitHub repository private during beta. Do not commit local databases, `.env` files, or secrets.
