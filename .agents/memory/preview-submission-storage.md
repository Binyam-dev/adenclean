---
name: Preview submission storage
description: Storage and privacy guardrails for customer request and cleaner availability intake.
---

Production storage is Appwrite (`ADENCLEAN_STORAGE=appwrite`); local SQLite is development and test only. Admins sign in with individual email and password accounts (scrypt hashes, managed with `create_admin.py`), with signed short-lived sessions keyed by `SESSION_SECRET`. Admin actions change internal statuses and keep a history; approval is not customer notification, cleaner assignment, or a confirmed booking.

**Why:** The records include names, email addresses, and service-area details, so they must not live in local files or behind a shared password.

**How to apply:** Before a public beta, define retrieval/deletion, retention, notifications, and customer disclosures; arrange backups (Appwrite free has none). Keep preview/test submissions out of launch data; never display or commit admin secrets.

Customer reviews and service-issue reports are private to AdenClean, not public testimonials. A request gets a high-entropy private feedback link; customers can submit one review and one issue report only after the service is marked complete. The customer can revisit the link to see issue status, but status changes do not send notifications.

**Why:** The preview has no customer accounts or connected email channel, so the private link scopes customer access without implying a confirmed booking or public review consent.

**How to apply:** Keep the link capability private and hashed at rest, require completed service before accepting feedback, and do not publish reviews or claim automated customer updates without an explicit product and privacy decision.
