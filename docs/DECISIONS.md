# Marketplace decisions

Defaults from the marketplace build brief (Nov 4, 2026). The owner can override any of them.
Every value marked "config" lives in `marketplace/config.py` and can change per environment
without a code change. Record each override here with a date.

| Decision | Default | Where it lives | Status |
| --- | --- | --- | --- |
| Model | Customer posts a job, cleaners quote, customer picks. The platform never sets a mandatory price. | Product rule, enforced in `marketplace/offers.py` | Assumed |
| Platform fee | 15% of the agreed price, charged to the cleaner (`PLATFORM_FEE_BPS=1500`). No customer fee. Stored per booking. | config | Assumed |
| Tips | 100% to the cleaner | `marketplace/money.py` | Assumed |
| Scope | Residential cleaning only, launch ZIPs listed in config | config | Owner to confirm ZIPs |
| Age | 18+ for both modes | Product rule | Assumed |
| Sign-in | Email one-time code (Resend); phone check for cleaners and for customers who book | Phase 1 auth | Assumed |
| Money | Stripe Connect Express, "separate charges and transfers"; funds held until completion; never an Aden bank account | Phase 2 | Assumed |
| Cancellation | Free more than 24 h before start; 25% to the cleaner inside 24 h (cleaner can waive); cleaner cancellations carry no money penalty | config | Counsel to review |
| Auto-confirm | 48 h after check-out with no dispute | config | Assumed |
| Counter-offers | At most 2 counter rounds per job-cleaner pair; price locks at acceptance | config | Assumed |
| Damage cap | $1,000 per booking, reserve-funded | config | Broker to price |
| Offer expiry | 24 h | config | Assumed |
| Job expiry | 72 h without an accepted offer | config | Assumed |
| Server instances | Exactly one, because Appwrite has no conditional updates or transactions | README, `marketplace/locks.py` | Constraint |

## Questions only the owner can answer

Asked and answered Nov 4, 2026:

| # | Question | Owner's answer | What it means for the build |
| --- | --- | --- | --- |
| 1 | Google Play account type and creation date | Type: personal ("iamdeveloping", ID 5732651492387344661). Creation date: unknown; Play Console does not show it on the account page. | Plan for the 12-tester, 14-day closed test. The account is still in Google's new-account identity verification, which points to a recent account. |
| 2 | Legal entity and EIN | In process | Stripe Connect live mode, 1099 reporting and Terms naming the platform wait for the entity and EIN. Test mode is unaffected. Launch gate. |
| 3 | Attorney opinion on classification before launch | Yes | Keep the marketplace model; the attorney opinion is a launch gate in `COMPLIANCE.md`. |
| 4 | Support email and phone | Same: applications@adeneats.com, (240) 342-6088 | Confirmed for store listings, policies and the app. |
| 5 | Who staffs vetting review and disputes | A role, not yet a named person | Admin console uses roles: `vetting_reviewer` and `dispute_reviewer`, both assignable to any admin. Until someone is named, the owner holds both. Name the person before the closed beta, because disputes have a 2-business-day target. |
