---
name: Preview submission storage
description: Storage and privacy guardrails for customer request and cleaner availability intake.
---

Customer requests and cleaner availability are saved in local SQLite for the Replit preview. The private preview admin uses one unique 12-character-minimum password from `ADENCLEAN_ADMIN_PASSWORD`, with signed short-lived sessions keyed by the existing `SESSION_SECRET`. Admin actions change internal statuses and keep a history; approval is not customer notification, cleaner assignment, or a confirmed booking.

**Why:** This is a low-dependency preview workflow, not a production account system. The records include names, email addresses, and service-area details, so both local storage and shared-password access need a production replacement.

**How to apply:** Before a public beta, move to durable storage, use per-user authentication and server-side roles, and define retrieval/deletion, retention, notifications, and customer disclosures. Keep preview/test submissions out of launch data; never display or commit admin secrets.

Customer reviews and service-issue reports are private to AdenClean, not public testimonials. A request gets a high-entropy private feedback link; customers can submit one review and one issue report only after the service is marked complete. The customer can revisit the link to see issue status, but status changes do not send notifications.

**Why:** The preview has no customer accounts or connected email channel, so the private link scopes customer access without implying a confirmed booking or public review consent.

**How to apply:** Keep the link capability private and hashed at rest, require completed service before accepting feedback, and do not publish reviews or claim automated customer updates without an explicit product and privacy decision.
