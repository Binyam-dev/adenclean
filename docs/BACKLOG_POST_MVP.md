# After the MVP

Ideas and known work that are outside version 1. Nothing here blocks store submission.

## Product

- Notify customers when a request is approved or completed (needs an email channel and a privacy-policy change; today the app sends no messages).
- Push notifications for status changes.
- Edit or cancel a request from the app.
- Show a cleaner's name on an assigned request (needs cleaner accounts).
- Spanish and Amharic translations of the app and the website.
- Public reviews, with explicit consent and moderation.

## Marketplace (built, switched off)

Turn it on only after: the attorney's classification opinion, the background-check disclosure review, insurance, a named person for vetting and disputes, live Stripe and Checkr accounts, and `python setup_appwrite.py` to create the new tables. Then set `MARKETPLACE_ENABLED=1` and build the app with `EXPO_PUBLIC_MARKETPLACE=1`. See `docs/COMPLIANCE.md`.

Open marketplace work: demo accounts and App Review notes showing Report and Block; admin pages for activating cleaners and releasing due payouts (the endpoints sit under `/api/v1/admin` and cannot be reached with the admin cookie); re-acceptance of changed terms; messaging; reviews; disputes.

## Website

- `hallmark-redesign` branch (local only): host the hero photo yourself and check its licence and alt text, convert fonts to WOFF2, then merge.
- Service pages for each cleaning type and a Silver Spring area page (see the SEO audit in `.hallmark/adenclean-seo-audit/`).
- Verify the site in Google Search Console and submit `sitemap.xml`.

## Engineering

- Two or more server instances: move bookings and status changes to a store with real transactions.
- Rate limits shared across instances.
- Lock file with hashes for Python dependencies.
- Replace the in-memory limit on admin lists (newest 100) with paging.
- End-to-end UI tests on a device or emulator.
- Automate backups from a server instead of the owner's PC.
