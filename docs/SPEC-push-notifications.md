# Spec: push notifications for request status (version 1.0.1), v2

Status: DRAFT v2 for owner approval, revised after the EGM review. No code written. Branch `spec-push` (off `main`, 05172a8).
Confidence tags: [Certain] checked in this repository; [Likely] from documentation or reasoning, not tested; [Guessing] filling a gap.

## Why

1. Google wants a genuine update during the 14-day closed test (`RELEASE.md`). The test has not started yet (Android build 3 is not uploaded; Play verification is pending), so there is slack.
2. A customer must now open the app and pull to refresh to learn a request was approved or completed. A notification closes that loop.
3. It is a native feature, which also lowers the Apple 4.2 risk, though that risk looks low without it [Likely].

It stays out of the first iOS submission: new data type on both privacy forms, server work, and two credentials from the owner's accounts.

## Scope (cut after review)

In: one notification when an admin changes a **customer request's** status; asking permission once after a request is sent; an off switch.
Out: issue-status pushes, review pushes, availability pushes, marketing pushes, per-type settings, notification history, email or SMS, web push, the marketplace, receipt-based cleanup, a 30-day cleanup job, `push_platform`.

## Behavior

### App (Expo, `expo-notifications`)
- After a request is sent (and when a request is added from a private link), the app offers **Turn on** or **Not now**. Never asked at launch. "Not now" is stored on the phone (secure storage, key `adenclean.push.declined`) and not repeated.
- **Turn on**: create the Android channel "Request updates" first, then ask for system permission, then get the Expo push token and register it for that request. If denied, say so once and point to Settings.
- More > Notifications: one switch, kept as a local flag. Turning it off sends `push_unregister` for each saved request's code with this phone's token and retries any that fail the next time the app opens. A request the server no longer knows (404) is ignored.
- Tapping a notification opens that request.
- Text is fixed and generic: "Update on your request. Tap for details." (the review recommended this over naming the service, because a lock screen is visible to others). Status is shown only inside the app.
- Without permission, on a simulator, or against an older server (404 on the new actions), the app behaves exactly as today.

### Server
- New module `push.py` (token rules, templates, sender, queue). New storage helpers live in `push.py` or a new `push_store.py`, not `store.py` (490 lines, limit 500). Edits to `store.py`, `main.py` and `admin_routes.py` are a few lines each [Certain: all three are near the limit].
- Actions added to `handle_customer_feedback` (`submissions.py`; today it accepts only `lookup`, `review`, `issue`): `push_register` and `push_unregister`, with the private code and the push token.
- Order of checks: wrong or malformed private code gives the existing 404 first, then a malformed push token gives 400. A bad code stores nothing.
- Token format: `^Expo(nent)?PushToken\[[A-Za-z0-9_-]{10,60}\]$`; stored in a VARCHAR 255 column.
- **Up to 3 tokens per request** (a person may have two devices). A new registration beyond 3 replaces the oldest. `push_unregister` removes only the token supplied. Tokens are stored in one column as a comma-separated list, with a hard cap on length.
- Own rate-limit bucket for the two actions, sized like the lookup bucket (a person may register or unregister up to 60 saved requests), keyed by address. The default 10 per 15 minutes would break that [Certain: `RATE_LIMIT_MAX_REQUESTS = 10`; app keeps up to 60, `MAX_SAVED`].
- **Sending** (the key fix): `push.send_async(request_id, new_status)` is called after the status change is saved and after any store lock is released. It puts a job on a bounded queue read by a single daemon worker thread (queue size 100; when full the message is dropped and logged). The worker makes **one** HTTPS call to `https://exp.host/--/api/v2/push/send` with a 5 s timeout, never retries, and catches every exception. The admin response never waits for it. This matters because the server is a stdlib `ThreadingHTTPServer`, where a blocking send would delay the admin's reply.
- Statuses that notify: `approved`, `declined`, `completed`, `cancelled`, and `pending` when reopened. Fixed text for all; send only when the status really changed.
- Final statuses (`completed`, `cancelled`): after the first send of that status the worker clears the request's tokens. This replaces any scheduled cleanup (the repo has no scheduler) [Certain].
- `PUSH_ENABLED=1` must be set or nothing is sent. Optional `EXPO_ACCESS_TOKEN` only if Expo's "enhanced security" is switched on [Guessing]. Optional `PUSH_CA_BUNDLE` for a TLS-inspecting network; certificate checking is never disabled.
- A dead token reported in Expo's immediate reply is removed. Receipts (which carry most `DeviceNotRegistered` results, about 15 minutes later) are not polled in 1.0.1. A dead token costs nothing but one rejected message [Likely].
- Logs: only the HTTP status and the error type. Never the token, Expo's reply body, an exception message or a traceback (the current request log is already safe: no query, body or token [Certain]).
- Test seam: `push.SENDER` is replaceable. Tests use a fake that raises, a fake that blocks on a `threading.Event`, and a localhost stub that never answers.

### Data
- `customer_requests` gets one optional column, `push_tokens` (VARCHAR 255). `setup_appwrite.py` adds missing columns when re-run [Certain]. **Run it before deploying**, or updates to the row fail.
- **Backup export (blocker found in review):** `export_all` returns whole rows today (`return {table: self._list(table, []) ...}`) and already includes `feedback_token_hash` [Certain]. `push_tokens` is removed from the export. A test fails if a schema column is added without being classified as exported or private. The admin list is safe: it uses the `LIST_FIELDS` whitelist [Certain]. The Appwrite console can still read the field; that is stated in the runbook.
- No API response, admin list, export or log line contains a push token. Request bodies do (the registration call), so the test is scoped to responses, logs and exports.

### Privacy and store forms (changes ship with the release)
- Apple App Privacy: add Identifiers > Device ID, linked, app functionality. [Guessing: Apple may treat a push token this way; decide against Apple's current wording before submitting 1.0.1.]
- Google Data safety: add Device or other IDs, collected, not shared, app functionality. Expo's push service delivers messages for us; whether Google calls that sharing needs confirming [Likely: service-provider processing is not sharing].
- `static/policies.html` line 87 says status changes do not trigger notifications. That becomes false and must be rewritten: what the token is, who delivers (Expo, Apple, Google), that it is removed after a final status and when notifications are turned off.
- `app.json`: add the Device ID type to `privacyManifests` (five types today). Check `expo-notifications`' own manifest and the `POST_NOTIFICATIONS` permission against the Play form.
- Update `mobile/store/LISTING.md`, `docs/STORE_REQUIREMENTS.md`, `docs/RUNBOOK.md`, `docs/SECURITY_REVIEW.md` in one checklist item.

### Native build and credentials
- `expo-notifications` needs a new native build; Expo Go cannot receive remote push on Android [Likely]. Bump `expo.version` to 1.0.1 (`app.json` says 1.0.0 [Certain]); EAS increments build numbers by itself.
- The plugin, the push entitlement and `android.googleServicesFile` go only in this branch, never into iOS build 8. `projectId` already exists in `app.json` [Certain].
- **Android (owner):** a Firebase project and an FCM v1 service-account key, uploaded with `eas credentials`; `google-services.json` placed in `mobile/`. [Likely]
- **iOS (owner):** an Apple push key, created during an interactive EAS build with the owner's Apple login, and the owner's iPhone registered for a preview build. [Likely]
- Norton TLS proxy on the development PC breaks Python's HTTPS to `exp.host`; use the fake sender locally and `PUSH_CA_BUNDLE`.

## Failure modes
Permission denied, uninstalled app, dead token, slow or down Expo, full queue, push disabled, older server: none affects the app's other functions or any admin action. A stolen private code lets its holder add a device for that request's notifications, which they could already read; accepted (256 random bits). The 3-token cap bounds abuse.

## Files touched (about 22)
Server: new `push.py`; edits to `store.py` (export), `submissions.py`, `admin_routes.py`, `main.py`, `.env.example`, `static/policies.html`; tests `tests/test_push.py` and additions to `test_app.py`.
App: `app.json`, `package.json`, `src/lib/push.ts` (+ test), `src/app/new.tsx`, `src/app/request/[ref].tsx`, `src/app/(tabs)/more.tsx`, `src/app/_layout.tsx`.
Docs: `LISTING.md`, `STORE_REQUIREMENTS.md`, `RELEASE.md`, `RUNBOOK.md`, `SECURITY_REVIEW.md`.

## Acceptance criteria
1. A status change on a registered request makes at most one send call, with only the fixed text, and tapping the notification opens that request.
2. With `PUSH_ENABLED` unset nothing is sent and nothing errors.
3. A raising sender and a never-answering sender leave the admin response under 1 s with the status saved (tested with a blocked `Event` and a localhost stub).
4. No push token appears in any API response, admin list, backup export or log line; a test fails when a schema column is added without being classified for export.
5. A wrong, malformed or missing private code returns 404 and stores nothing; a malformed push token returns 400; the fourth token on a request replaces the oldest; unregister removes only the supplied token.
6. Registering and unregistering 60 saved requests in a row is not rate limited.
7. The app ignores a 404 from an older server, retries failed unregisters on next open, and works unchanged when permission is denied or on a simulator.
8. Policy page, privacy manifest, listing and both store forms list the new data type before 1.0.1 is submitted.
9. Server and mobile checks pass. Manual, on real devices through a preview build: register on an Android phone and an iPhone, change a status in the admin page, see the notification, tap it, turn notifications off and confirm nothing arrives. Tests use synthetic tokens and fake codes only.

## Risks
- Two owner credentials (Firebase, Apple push key) must exist before anything can be sent.
- Apple and Google may classify the token differently from my guess.
- Cannot be fully verified without physical devices.
- About 3 to 5 days of work plus credential setup; the closed test must not wait for it (it can start on build 3 as is).

## Alternatives for the 1.0.1 slot
- **A (this spec):** push on both platforms in 1.0.1.
- **B:** Android-first push; iOS push in a later version. Less credential work now, but iOS gets no 4.2 help.
- **C:** 1.0.1 is fixes from tester feedback (cheapest, honest evidence for Google's form); push becomes 1.0.2.

## Open questions for the owner
1. Which alternative: A, B or C? (Recommendation below.)
2. OK to create a Firebase project under your Google account for Android push, after iOS build 8 is submitted?
3. Notification text "Update on your request. Tap for details." OK?
