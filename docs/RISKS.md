# Marketplace risks

Ordered by severity. Every pull request that trades one of these for another says so in its
description.

| # | Risk | Mitigation | Owner action |
| --- | --- | --- | --- |
| 1 | Cleaners classified as employees (Maryland presumes employment under the ABC test; the hiring party carries the burden). | Cleaner sets price, chooses jobs, hours, supplies and method; no auto-assignment, quotas, exclusivity or penalties for declining; config-driven fallback to a W-2 model. Enforced in code and tested. | Written opinion from a Maryland employment attorney before launch. |
| 2 | A serious safety incident in a customer's home. | Identity and FCRA-compliant background checks, address hidden until booked and paid, check-in and check-out, safety button, incident runbook, insurance. | Bind insurance; staff a 24-hour safety contact. |
| 3 | Marketplace liquidity failure (an empty side). | Supply first: 30 vetted cleaners in launch ZIPs before opening demand; expand ZIP by ZIP; track fill rate and time to first offer. | Recruit cleaners. |
| 4 | Payment disputes and chargebacks. | Funds held in Stripe until confirmation; evidence capture; reserve; append-only ledger with idempotency keys. | Approve Stripe Connect live mode. |
| 5 | Customers and cleaners moving off-platform. | Phone numbers, emails and links are rejected in job notes, offers and names (a speed bump that is easy to evade; reports are the backstop); contact details hidden until booking; in-app chat with masking; payment protection, reviews and repeat-booking discount as reasons to stay. | Counsel reviews anti-circumvention terms. |
| 6 | Single-instance architecture (Appwrite: no transactions, no conditional updates). | Process-wide lock with a status check inside it; documented one-instance limit; move acceptance and ledger to a transactional store if volume grows. | Keep Render at one instance. |
| 7 | Free Render hosting sleeps (about a minute to wake), delaying offers and store review. | Move to the Starter plan ($7/month) before the closed beta and before any store review. | Approve the upgrade. |
