# Spec: report and block (user-generated content), v2

Status: DRAFT v2 for owner approval, revised after the EGM review. No code written. Branch: `moderation` (off `main`, 53d35a9).
Confidence tags: [Certain] checked in code or docs; [Likely] reasoned, not tested; [Guessing] my judgment.

## Why

App Store guideline 1.2 requires, for any app with user-generated content: a way to filter objectionable material; a way to report content with timely responses; a way to block abusive users; published contact information; and terms that forbid objectionable content. The marketplace has user text: job notes (800 characters), offer messages (500) and display names. Without these, the marketplace build is likely to be rejected. [Likely]

## Scope

In: report a job or an offer; block the person behind one; a filter on text before it is saved; an admin queue with actions; mobile screens; tests.
Out: reporting a bare user or display name (job and offer already carry the author), chat, photos, reviews, automated moderation, appeals, auto-suspension on report count. Each later feature must add its own report entry point.

## Facts about the current code that shape the design [Certain]

- `current_user` returns 401 for any account whose status is not `active`, on every request. A suspended person loses everything at once, including pay, check-in and cancel.
- `accept_offer` checks only the job's status under `BOOKING_LOCK`. `v1_create_offer` takes no lock. `BOOKING_LOCK` is not reentrant.
- API views carry no user ids: `_job_view` has no customer id and `_offer_view` has no cleaner id.
- Cancel and account deletion null out job notes and offer messages.
- `enforce_rate_limit` is in memory, per IP, 15-minute window.
- Nothing sets or clears `suspended` today.

## Behavior

### Reporting
- Entry points: on a job's notes, and on an offer (its message and cleaner). No id of a person is exposed; the target is the job or offer id.
- `POST /api/v1/reports` `{targetKind: "job"|"offer", targetId, reason, detail?}`. Reasons: `spam`, `harassment`, `unsafe`, `off_platform`, `fake`, `other`. Detail up to 500 characters.
- Visibility: one shared `can_view(user, kind, id)` helper, also used by the feeds. It is evaluated at report time. Blocked and closed items stay reportable. A missing target and an invisible one both return the same 404.
- Self-reports are rejected. A second report by the same person on the same target is merged: the existing open report is returned with 200 and nothing new is written. After a dismissal the person may report again.
- Limit: 10 new reports per person per hour, counted from the `reports` table by `reporter_id`, not by IP. Merged reports do not count. Block and unblock calls are limited to 30 per hour.
- The report stores a snapshot: the reported text, the author's display name, and the job or offer status at report time. Snapshots are kept 12 months after resolution, then cleared by an admin sweep. [Guessing: retention period needs counsel.]
- The reported person never sees who reported. A test scans every `/api/v1` response to confirm the reporter id never appears.
- Reporter confirmation: "Thanks. We review every report within 24 hours. Questions: <support email>."

### Blocking
- `POST /api/v1/jobs/{id}/block` and `POST /api/v1/offers/{id}/block` block the other person on that job or offer. `POST /api/v1/blocks/{blockId}/remove` unblocks. `GET /api/v1/blocks` lists my blocks with a display name and a block id (not a user id).
- Effect, one way: the blocker no longer sees the blocked person's offers or jobs, and the blocked person's open jobs and offers are hidden from the blocker. The blocked person's offers on the blocker's open jobs are withdrawn (pending and countered, in both roles). Visibility is computed from the block row when reading, so a missed sweep cannot leak.
- A new offer across a block is refused with the same 404 as a missing job, so the block cannot be inferred.
- A pair with an active booking is exempt from hiding. The booking continues; money and safety flows keep working. Unblocking does not restore withdrawn offers.
- Blocking is private; the other person gets no notice.
- Writes order: write the block row first, then run an idempotent sweep.

### Filter (before save)
- Applies to job notes, offer messages and explicit display names. Never re-applied to existing users. For a new sign-up the name is checked before the one-time code is consumed, so a rejected name does not burn the code.
- Rejects with HTTP 400 and a plain message: phone numbers (10 or more digits, with common separators, so times, ZIP codes and street numbers pass), email addresses, links (`http`, `www`, and a bare domain with a common ending), and a list of 20 to 50 abusive terms matched as whole words after lowercasing. No character-swap normalization in v1.
- The list is data in `marketplace/moderation.py`, owner-maintained, reviewed quarterly. It is a speed bump, not a fix for `RISKS.md` #5 (that item describes masked chat, which does not exist yet). A fixtures test has 12 or more clean and dirty samples, including addresses, gate codes and times that must pass.

### Admin
- Endpoints live under `/api/admin/moderation`, because the admin cookie is only sent under `/api/admin`. The routing alias in `main.py`, now hard-coded to vetting, becomes a small table of prefixes.
- `GET` lists open reports, oldest first, with the snapshot text, reason, target status and the open-report count for that author.
- `POST /api/admin/moderation/{report_id}` actions by target:
  - `dismiss` (any report);
  - `remove_content` (clears the job's notes or the offer's message; the snapshot is kept);
  - `suspend_user` (the author of the target);
  - `cancel_booking_refund` (only if the target's job has a booking: runs the existing cancel and refund path, as the customer's full refund, with no late fee).
- A resolved report returns 409 on a second action. The report records `status`, `resolved_at` and a short action name, plus the admin email.
- `suspend_user` is always allowed on an active account, with a warning shown when a booking is live. It never resurrects a deleted account. A suspended person may still sign in to delete their account and read their own bookings; they cannot post, offer, accept or sign in to new sessions. `unsuspend_user` reverses it. [This needs a status-aware `current_user`: see below.]
- Admin page: a Reports tab with the open count on the tab.
- New-report alert: one email to the support address (config key, default `applications@adeneats.com`) when `MAIL_MODE=resend`. It never goes to the reported person or the reporter, never contains the reporter id, and a send failure never fails the report.

### Status-aware sign-in
- `current_user` keeps returning 401 for `deleted`. For `suspended` it returns the user with a flag, and every write route refuses suspended users with a 403 and a plain message, except: read my own bookings, cancel-booking, check-in and check-out, and delete account. [Likely: this is the smallest change that makes AC 6 true.]

### Locks and races
- All moderation writes (block, unblock, suspend, remove_content, cancel) take `BOOKING_LOCK`. Moderation code never calls the accept or cancel paths from inside the lock; it calls their inner functions.
- `accept_offer` re-reads the user status and the block row after taking the lock and returns 409 on a block or suspension. `v1_create_offer` re-checks blocks. Two threaded tests: accept versus block, accept versus suspend.

### Terms and App Review
- The Terms page gets a clause: no objectionable, abusive, harassing or unsafe content; AdenClean may remove content and accounts. The clause is shown at sign-in. `TERMS_VERSION` is bumped so existing users re-accept. Counsel reviews the wording. [Guessing: wording is mine, not legal advice.]
- The More screen shows the support email. App Review notes explain where Report and Block are, with a demo account that reaches both in two taps.

## Data

Two new tables in `marketplace/schema.py`, created by `setup_appwrite.py`. Indexed columns are VARCHAR. Nullable columns are not required.
- `reports`: `id`, `reporter_id`, `target_kind`, `target_id`, `target_user_id`, `reason`, `detail`, `snapshot_text`, `snapshot_name`, `snapshot_status`, `status` (`open`, `dismissed`, `actioned`), `action`, `created_at`, `resolved_at`, `resolved_by`. Indexes: `status`, `reporter_id`, `target_user_id`. No unique index; open reports are de-duplicated in code under the lock.
- `blocks`: `id`, `blocker_id`, `blocked_id`, `created_at`. Unique on `blocker_id` + `blocked_id`; index on `blocked_id`. Block is idempotent.
- Storage needs: `find()` with ascending order and a count.
- Account deletion clears the person's own report `detail` and deletes their blocks; reports about them keep ids and snapshots for abuse history.

## Files touched (about 20)

New: `marketplace/moderation.py`, `api_v1_moderation.py`, `static/admin-moderation.js`, `tests/test_moderation.py`, `tests/test_moderation_api.py`, mobile report sheet and blocked-list screens and `lib/moderation.ts` with tests.
Changed: `api_v1.py` (routes, `can_view`, filter on save, status-aware `current_user`), `marketplace/locks.py`, `marketplace/schema.py`, `marketplace/storage.py`, `marketplace/accounts.py`, `marketplace/mailer.py`, `main.py`, `static/admin.html`, `static/admin.js`, `static/policies.html`, `mobile/src/lib/v1.ts`, job and offer screens, More screen, `tests/test_static_integrity.py`, `docs/COMPLIANCE.md`.

## Acceptance criteria

1. Reporting a job or offer you cannot see returns the same 404 as a missing one. A duplicate open report returns the existing one. The 11th new report in an hour is refused.
2. After a block the two people do not see each other's open jobs or offers, offers across the block are refused with the missing-job 404, the blocked person's pending offers are withdrawn, and an existing booking still completes.
3. Text with a phone number, email, link or listed term is rejected with a clear message; at least 12 fixtures pass or fail as expected; a rejected name does not consume the sign-in code.
4. Admin actions work from a browser with the admin cookie (a test asserts the URLs are inside the cookie path) and record who and when. A resolved report returns 409.
5. A suspended person cannot post, offer, accept or start a new session, but can finish a live booking and delete their account. `unsuspend_user` restores them.
6. `cancel_booking_refund` cancels and refunds a booked job in full once, and the ledger reconciles.
7. Threaded tests pass for accept versus block and accept versus suspend.
8. No `/api/v1` response contains the reporter's id (a scan test).
9. Full Python suite and mobile typecheck and tests pass, and these screens are checked in the browser: report sheet, blocked list, admin Reports tab.

## Risks

- The word filter is easy to evade and can block innocent text. Reports are the backstop.
- The 24-hour response is an operating promise: the owner reads the queue daily. This is a release gate for the 24-hour wording.
- A customer who feels unsafe mid-booking has only cancel and support. Hiding does not apply during a booking.

## Open questions for the owner (recommended answers from the review)

1. Suspension during a booking: always allowed, with a warning, and an admin cancel-and-refund action exists. Recommended: yes.
2. Alert email: `applications@adeneats.com` by config, and you read the queue every day. Recommended: yes.
3. Phone numbers and emails in text: reject. Recommended: reject, not mask.
4. Short abusive-word list in the repo, owner-maintained, reviewed quarterly. Recommended: yes.
