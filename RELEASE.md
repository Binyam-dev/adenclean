# Releasing AdenClean

How to build, ship and update the app, and where each store release stands. Update the tracker tables as things happen; they are the record the Google production-access form asks about.

Bundle ID and package: `com.adencommunity.clean` (confirmed: it is already attached to the App Store Connect record 6830724671 and the EAS project, so it cannot change).

## Where we are (updated 2026-11-13)

| Store | Status | Next step | Owner |
| --- | --- | --- | --- |
| Apple | Build 8 finished on EAS. Not submitted. | Render Starter plan, then upload screenshots and press Submit for Review (see "Submit to Apple"). | Owner |
| Google Play | Build 3 (`.aab`) finished. Not uploaded: the Play account is still in identity verification. | Finish verification, create the closed test, recruit testers (`docs/PLAY_TESTING.md`). | Owner |
| Server | Live on Render free plan. | Move to Starter before either store review. | Owner |

## Google Play closed-test clock

Personal developer accounts created after 2023-11-13 must run a closed test with at least 12 testers opted in continuously for 14 days before applying for production. Internal testing does not count. Source: support.google.com/googleplay/android-developer/answer/14151465. Google's review of the production application usually takes 7 days or less.

| Item | Value |
| --- | --- |
| Account type | Personal ("iamdeveloping") |
| Account creation date | Unknown. If the Play Console dashboard shows a closed-testing requirement card, it applies. |
| Identity verification | Not complete as of 2026-11-13 (trader status, Android device sign-in, phone verification) |
| Closed test created | not yet |
| Testers invited (target 20 or more) | 0 |
| **Clock start date** (the day 12 or more are opted in) | not started |
| **Earliest production application date** (start + 14 days) | n/a |
| Production access applied | no |

### Opted-in tester count

Count the testers who accepted the opt-in link, from Play Console > Testing > Closed testing > Testers. Add a row every time you check, at least every other day. A tester who opts out resets that person's days, so recruit past the minimum.

| Date | Invited | Opted in | Notes |
| --- | --- | --- | --- |
| | | | |

### Updates shipped during the test

Google looks for evidence of real testing, so ship at least one genuine update while the test runs. The plan is version 1.0.1 with push notifications for request status (see `docs/DECISIONS.md`).

| Date | Version / build | What changed and why |
| --- | --- | --- |
| | | |

### Tester feedback and fixes

The production-access form asks how you recruited testers, what feedback you got and what you changed. Keep this table honest and specific.

| Date | Tester feedback | Fix, or why not | Version |
| --- | --- | --- | --- |
| | | | |

## Build

```bash
cd mobile
npm ci
npm run typecheck && npm run lint && npm test
npx eas-cli@latest build --platform all --profile production
```

- Builds run in Expo's cloud. Credentials for both platforms already exist on EAS (account `binyam4u`).
- Build numbers go up by themselves (`appVersionSource: remote`, `autoIncrement`). Change the user-visible version only in `mobile/app.json` (`expo.version`) when you ship a new version.
- The production profile points the app at `https://adenclean.onrender.com`. A store build fails on purpose if that address is missing, not https, or localhost.
- Windows with Norton: set `NODE_EXTRA_CA_CERTS=C:\ProgramData\Norton\Antivirus\wscert.pem` first, or EAS login and uploads fail on a certificate error.
- Do not build with `EXPO_PUBLIC_MARKETPLACE=1`. That switches on the unfinished marketplace screens and the payment SDK.

## Submit to Apple

1. Render is on the Starter plan (no cold start for the reviewer).
2. `npx eas-cli@latest submit --platform ios --profile production` (uploads the latest build to App Store Connect and TestFlight), or attach the build in App Store Connect.
3. In App Store Connect, version 1.0: choose the build; upload both screenshot sets from `mobile/store/screenshots/ios-6.3/` and `ios-6.9/`; paste text from `mobile/store/LISTING.md`; answer App Privacy from the table there; answer the age-rating questionnaire "None" throughout (result 4+).
4. App Review notes: paste the notes from `LISTING.md`, with the demo link from `%LOCALAPPDATA%\AdenClean\apple-review-demo-link.txt`. The demo request (`E530B601923D`) must stay in place and complete while the app is in review. Checked on 2026-11-13: status completed, no review or issue yet.
5. Press **Submit for Review**. This is the owner's click.

## Submit to Google Play

1. Create the app in Play Console (name AdenClean, free, `com.adencommunity.clean`).
2. Testing > Closed testing > create a track > upload the `.aab` from the EAS build page > add testers (`docs/PLAY_TESTING.md`) > roll out.
3. Fill in Data safety, content rating and the store listing from `LISTING.md`.
4. After 14 days with 12 or more opted in: Dashboard > Apply for production access, answering from the tracker tables above.
5. After approval: create a production release with the tested build (or a newer one) and roll out.

## Ship an update

1. Change the app, bump `expo.version` in `mobile/app.json` if it is user-visible, run the checks above.
2. Build and submit as above. iOS needs a new version page in App Store Connect and a new review; Android uses the same closed-test track while testing, production afterwards.
3. Log it in "Updates shipped during the test" while the test runs.
4. A server-only fix needs no store release: merge to `main` and Render deploys.

## Server releases

Merging to `main` deploys to Render automatically. Check `https://adenclean.onrender.com/health?deep=1` afterwards, and run `python scripts/smoke_test.py https://adenclean.onrender.com`. Details, rollback and recovery: `docs/RUNBOOK.md`.

## Before every submission

1. **Cold-server smoke test** with the server on the Starter plan: wait 20 minutes with no traffic, then `python scripts/smoke_test.py https://adenclean.onrender.com` and time it. The first request should answer in seconds, not a minute.
2. **Listing matches the app:** `mobile/store/LISTING.md` privacy answers equal what the app collects (name, email, typed town or ZIP, request notes, reviews and issue reports; no tracking, no analytics, no payment SDK).
3. **Apple review guidelines** (developer.apple.com/app-store/review/guidelines): 2.1 the demo works with no login and the server is up; 4.2 the app is native, not a website wrapper (native tabs, secure on-device storage, status checks); 5.1.1 privacy policy URL works and matches; 5.1.1(v) no account creation, so no in-app account deletion needed (the deletion-request route is in More); 1.2 reviews are private to the business and never displayed to other users, stated in the review notes.
4. **Google Play policy** (support.google.com/googleplay/android-developer): Data safety matches the app; privacy policy link works; target API 36 (Expo SDK 58 default); the 16 KB page-size status shown in Play Console after upload.
5. `npm audit` and `pip-audit` show nothing new that matters (`docs/SECURITY_REVIEW.md`).
