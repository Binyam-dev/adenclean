---
name: Preview submission storage
description: Storage and privacy guardrails for customer request and cleaner availability intake.
---

Customer requests and cleaner availability are currently saved in local SQLite for the Replit preview. The API accepts submissions only; the app has no authenticated view for reading or managing them.

**Why:** The workflows needed persistence without introducing an external service, while account access, admin review, contact follow-up, privacy policies, and the private beta remain separate planned work. These records include names, email addresses, and service-area details, so preview storage is not a production-ready data plan.

**How to apply:** Before public beta or adding an admin list, choose durable storage and define authentication/authorization, retrieval and deletion, retention, and customer disclosures. Keep preview/test submissions out of any launch data.
