# Spec: cleaner app and instant dispatch (version 2) - DRAFT v2

Status: for owner approval. Nothing is built. Version 1 (request-only, PR #10 push) ships first and is not touched by this.
v2 changes from v1 of this draft: owner chose same-day only and a fixed price per service; fixes from the goldfish review (claim, states, races, eligibility data, phasing).

## Goal

A customer asks for a same-day cleaning. Eligible vetted cleaners are alerted at once and can accept (at their own price) or decline. The customer picks among those who accept. If nobody accepts in time, the request is posted to the job board so cleaners can still make offers. [Certain: owner's model, 2026-11-13]

## Decisions made

- Same-day only. A request is for today, with a start window at least 2 hours out (config `DISPATCH_MIN_LEAD_MINUTES`, default 120). Scheduled jobs keep using the board.
- **The cleaner sets the price** (owner, 2026-11-13, replacing "fixed price per service"). Each cleaner keeps a standing flat price per service they offer (`rates`, cents, set in the Availability screen). Accepting an alert means making an offer at that price (assumed: no per-job editing in the instant path).
- **Anyone who is capable and vetted can take the job** (owner). Capable = the cleaner offers that service. There is no invite list or ranking.
- **The customer chooses among the cleaners who accepted** (owner confirmed 2026-11-13; replaces "first accept wins"). Accepts arrive as offers for a short window; the customer taps one and the existing `accept_offer` books it. If a cleaner accepts and the customer has not chosen, the cleaner sees "waiting for the customer" and the offer expires with the window. No auto-booking.
- Wait before falling back to the board: config default 10 minutes (not a decision).
- One flag only: `MARKETPLACE_ENABLED`. Dispatch is on when the marketplace is on and `DISPATCH_WAIT_MINUTES` is set above 0.

## What exists (built, off) and what it cannot do

Jobs and their transitions (`jobs.py`), offers (`offers.py`), an atomic accept (`locks.py`, process-local `BOOKING_LOCK`), bookings (`bookings.py`), vetting, report and block, accounts. Gaps this spec must fill (found by review):

1. `accept_offer` needs an offer and an `open` job. A dispatch alert has neither.
2. No job state or transition means "asked" or "instant to open".
3. Claim and booking creation are two saves; a failure between them leaves a booked job with no booking.
4. Users have only `status` and `home_zip`. No availability flag, no per-cleaner service area, no location, no calendar. `service_zips` is one global list.
5. Cancellation fees measure from noon UTC on the start date, meaningless same-day. Cleaner cancellations carry no penalty.

## Design

### Data
- New table `dispatches`: `id`, `job_id`, `status` (`asking`, `claimed`, `fallback`, `cancelled`), `expires_at` (UTC, saved, not a timer), `chosen_offer_id`, `created_at`.
- New table `dispatch_asks`: `dispatch_id`, `cleaner_id`, `status` (`asked`, `declined`, `lost`, `won`), `asked_at`.
- Users get: `available_now` (boolean, cleaner toggles in app, auto-off after 4 hours), `service_zips` (list of ZIPs the cleaner works in, set by the cleaner, max 10), `rates` (flat price in cents per service the cleaner offers, within the configured min and max).
- Jobs get a field `instant` (boolean). Job states are unchanged; an instant job stays `open` while asking. The dispatch row, not the job, holds the asking state. It is also posted on the board only after fallback (hidden from the board list while its dispatch is `asking`).

### Accepting and choosing (reuses the existing offer path)
- A cleaner's Accept calls `make_offer` for the instant job (it is `open`, so the existing precondition holds) at their standing price, after re-checking eligibility under the lock (below). The ask row becomes `offered`.
- The customer sees offers arrive live (price, first name, verified badge) and taps one; that calls the existing `accept_offer`/`accept` path, which already books atomically against other offers. Other offers close.
- The dispatch row only tracks the window: `asking` until the customer chooses, the window ends, or the customer cancels; then `claimed` or `fallback` or `cancelled`. Accepting an offer after `expires_at`, after cancel, or after fallback is refused with "This request is no longer available."
- Remaining gaps from the review, kept: if booking creation fails after the job is saved as booked, the startup repair reopens any `booked` job without a booking. Order of saves: booking, job, dispatch, asks.
`BOOKING_LOCK` is per process. The server runs one process (same limit as push, `BACKLOG_POST_MVP.md`); two instances would need a real transactional store, so v2 must not be scaled out first.

### Timeout and restart
A sweeper thread runs every 15 seconds and at startup. For each `asking` dispatch with `expires_at` past, or with every ask declined, under the lock it sets `fallback`, posts the job to the board, and notifies the customer once. A restart loses nothing because `expires_at` is stored.

### Customer cancel
Customer cancel sets the dispatch `cancelled` under the lock; a later accept is refused. After a claim, normal cancellation rules apply, with a same-day rule (below).

### Payment
The customer pays when a cleaner is booked, as today (Stripe test mode in development). If unpaid after 30 minutes the booking cancels, the job reopens to the board, and the cleaner is told. Check-in still requires payment.

### Same-day cancellation rules (new, to approve)
Customer cancels before a cleaner accepts: free. After accept and more than 60 minutes before start: free. Within 60 minutes or no-show: fee as `money.py` sets for late cancel. Cleaner cancels after accepting: the job returns to the board at once with a one-line reason, and the cleaner's account gets a strike; three strikes in 30 days suspend dispatch alerts pending admin review. Exact numbers for the owner to set.

### Eligibility (asked only if all are true, at dispatch and again when the cleaner accepts)
Vetting approved and current; account active; offers this service and has a price set for it; `available_now`; job ZIP in cleaner `service_zips` (a cleaner who wants "anywhere" lists their ZIPs; the owner can widen this to a whole-area default); not blocked or hiding (`hidden_between`); no overlapping booking the same day. Everyone eligible is asked at once; there is no "nearest N" in v2.

### Cleaner alerts
Push to each asked cleaner with fixed generic text ("New cleaning request nearby. Tap to view."), no name, address or notes. Same Expo path as PR #10, with tokens stored per user (not per request) in a new column; the cleaner app screens open the dispatch by id. Push is best effort; the timeout never depends on delivery, and a cleaner can also see open asks in the app.

### App
One app, role-based (cleaner sees cleaner tabs). This is new work: the tab layout currently has one set of tabs and only content changes by role. Cleaner tabs: Requests (live asks, Accept/Decline, countdown), My jobs, Availability (toggle and ZIPs), Account. A separate cleaner app is not planned; it would add a second listing, review and privacy forms.

## Acceptance criteria

- Many cleaners can accept; exactly one offer is booked when the customer chooses, even if the customer taps two offers at once (parallel test); the others close within 1 s.
- A cleaner without a price for the service, or not offering it, is never asked.
- A rate below the minimum or above the maximum is refused on save and on offer (tests at min-1, min, max, max+1); a rate that falls outside after the limits change is skipped, and the cleaner is asked to update it.
- Each eligibility rule has a test where it alone excludes the cleaner, at dispatch and at claim.
- Timeout, all-declined and zero-eligible each produce one board job and one customer notification; zero-eligible falls back immediately.
- Accept after expiry, after customer cancel, or after fallback is refused.
- A failure injected between booking and job save leaves no booked job without a booking (repair test).
- Restart during `asking` still falls back at `expires_at`.
- Push carries no personal data; tokens never logged; a failing push does not stop the board fallback.
- The price the customer taps equals the booking price (offers cannot be edited after they are shown).
- A cleaner with a role switch sees only cleaner screens; a customer never sees cleaner screens (UI tests).
- All of it is off unless `MARKETPLACE_ENABLED=1`.

## Open questions for the owner

1. ~~Customer chooses or auto-book~~ Decided: the customer chooses.
2. ~~Price limits~~ Decided: yes. Each service has a minimum and maximum flat price (config `SERVICE_PRICE_LIMITS`, cents). The server refuses a rate outside them when the cleaner saves it, and again when an offer is made, so changing the limits never lets an old out-of-range rate be offered. **The dollar amounts are the owner's to set before launch; none are assumed here.** Original note: may a cleaner set any price? Without a floor or ceiling a cleaner can price at $1 or $1,000. Suggest a configurable min and max per service.
3. **"Capable":** offering the service in their profile, or something verified (a skills check, years, equipment)? Default here: profile only, plus vetting.

## Risks (first)

- **Launch blockers, not options:** attorney classification opinion, background-check disclosure review, insurance, a named person for vetting and disputes, live Stripe and Checkr accounts, admin pages for activating cleaners and releasing payouts. Without these, dispatch must not go live. [Certain]
- **Safety:** instant dispatch removes the customer's chance to choose who enters their home. Mitigation to decide: show the cleaner's first name, photo and verified badge before the customer confirms the booking, with a 2-minute decline window, or accept the risk with the attorney's view.
- Store review: sign-in, user content, payments and background checks each add scrutiny.
- Alerts depend on Expo, Apple and Google, which can be late. [Likely]
- Cleaner devices and tokens are personal data: policy page, Apple label and Data Safety need updates.
- Customer push (PR #10) is untested on real devices and v2 builds on it.

## Phases (each shippable and testable on its own)

1. Cleaner mode and availability: role-based tabs, `available_now`, `service_zips`, existing board (jobs/offers) for cleaners. No dispatch.
2. Dispatch rows, `claim_dispatch`, sweeper and fallback on the server, fully tested with a fake clock; no UI.
3. Cleaner alerts: push to cleaners, Requests screen with Accept/Decline.
4. Same-day pricing and cancellation rules, payment timeout.
5. Admin view of dispatches (who was asked, who won); privacy and store forms.
6. Real-device test with Stripe test mode and Checkr sandbox only; then the launch blockers above.

## Not in scope

Messaging, ratings that affect order, surge pricing, several cleaners per job, recurring or scheduled instant jobs, "nearest N" widening, a separate cleaner app.
