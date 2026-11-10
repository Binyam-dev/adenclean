# AdenClean store listing

Everything to paste into App Store Connect and Google Play Console. Every claim here is
true of the app as built; if the app changes, change this file with it.

Server: `https://adenclean.onrender.com`. Move it to Render's Starter plan before submitting, so reviewers never wait on a sleeping server.

## Names and links

| Field | Value |
| --- | --- |
| App name (both stores) | AdenClean |
| Bundle ID / package | `com.adencommunity.clean` |
| Support URL | `https://adenclean.onrender.com/` |
| Privacy policy URL | `https://adenclean.onrender.com/policies.html#privacy` |
| Support email | applications@adeneats.com |
| Support phone | (240) 342-6088 |
| Primary category | Lifestyle |
| Price | Free |

The support email and phone are the ones already published on the AdenClean website.
Confirm they are the ones you want customers to use before you submit.

## Apple App Store

**Subtitle** (30 max): `Request a home cleaning`

**Promotional text** (170 max):
Tell us what needs cleaning and when. AdenClean reviews each request, and you can check its status right in the app.

**Keywords** (100 max, comma separated, no spaces):
`home cleaning,house cleaning,cleaner,deep clean,move out clean,apartment,Silver Spring,Maryland`

**Description** (4000 max): use the full description below.

**What's new in this version:** First release.

**Copyright:** 2026 Aden Community Ventures LLC

**Age rating:** 4+. In the questionnaire answer "None" or "No" to every item. The app has
no user-generated content that other people can see: reviews go privately to AdenClean.

**Screenshots:** upload both sets, six images each, in order: `store/screenshots/ios-6.3/`
(1206 x 2622, the iPhone with Dynamic Island "medium display" set Apple requires) and
`store/screenshots/ios-6.9/` (1320 x 2868). Apple's page is inconsistent about which set is
mandatory, so supplying both is the safe choice. The app is iPhone only, so no iPad
screenshots are needed.

### App Privacy ("nutrition label")

Data is collected only when the person sends a form. Nothing is used for tracking or
advertising.

| Data type | Collected | Linked to the person | Used for |
| --- | --- | --- | --- |
| Contact Info > Name | Yes | Yes | App functionality |
| Contact Info > Email address | Yes | Yes | App functionality |
| Location > Coarse location (the town or ZIP code they type) | Yes | Yes | App functionality |
| User Content > Other user content (request notes, reviews) | Yes | Yes | App functionality |
| User Content > Customer support (service issue reports) | Yes | Yes | App functionality |

Apple's pages do not say whether a typed town or ZIP counts as location, so it is declared
as Coarse location to be safe. The same answers are written into `ios.privacyManifests` in
`app.json`, so the binary and the label agree.

Tracking: **No**. Third-party advertising: **No**. Analytics: **None** in the app. No
crash-reporting SDK is in the app (see `docs/DECISIONS.md`); if one is added, add Crash
Data, Performance Data and Other Diagnostic Data here and in the Play Data safety form.
Encryption: the app uses HTTPS only, so answer "No" to non-exempt encryption
(`ITSAppUsesNonExemptEncryption` is already set to false).

### Notes for App Review

> No sign-in is needed. The app has no accounts.
>
> To try the main flow: tap "Request a cleaning", choose a service, a day and a time of
> day, enter any name, an email address and "Silver Spring", agree, and send. The request
> then appears under "Requests".
>
> Reviews and problem reports only open after AdenClean staff mark a service complete. To
> see them, open the Requests tab, find "Sent a request from the website?", and paste
> this private link:
>
> `PASTE THE DEMO LINK HERE` (saved outside the repo in `%LOCALAPPDATA%\AdenClean\apple-review-demo-link.txt`)
>
> It belongs to a demo request that is already marked complete. Nothing is paid for in the
> app. Contact: applications@adeneats.com, (240) 342-6088.

The demo request already exists: reference `E530B601923D`, named "APPLE REVIEW DEMO - do not contact", status Completed (made 2026-11-04). Keep it while the app is in review. The link is kept out of the repo because anyone holding it can post a review for that request.

Account deletion: the app has no accounts, so Apple's account-deletion rule does not
apply. People can ask AdenClean to delete their information from More, and can remove saved
requests from their phone at any time.

## Google Play

**Short description** (80 max):
`Request a home cleaning in Silver Spring, MD and follow it from your phone.`

**Full description** (4000 max): use the full description below.

**Graphics:**
- App icon, 512 x 512: `store/play-icon-512.png`
- Feature graphic, 1024 x 500: `store/play-feature-graphic-1024x500.png`
- Phone screenshots: `store/screenshots/android-phone/` (1080 x 2160, six images)

**Category:** Lifestyle. **Contact email:** applications@adeneats.com.

**Content rating questionnaire:** answer "No" throughout. Expected result: Everyone.

**Target audience:** 18 and over. The app is not aimed at children.

**Ads:** None. **Financial features, health, news, government:** none.

### Data safety form

| Question | Answer |
| --- | --- |
| Does the app collect or share user data? | Collects: yes. Shares with other companies: no. |
| Data types collected | Name, email address, approximate location (the town or ZIP code typed in; Google's pages do not say whether typed input counts, so it is declared to be safe), other user-generated content (notes, reviews, reports) |
| Is collection required or optional | Required to send a request; notes are optional |
| Why it is collected | App functionality |
| Is data encrypted in transit | Yes (HTTPS) |
| Can people ask for their data to be deleted | Yes: by email from the app (More > Ask AdenClean to delete my information) and as described in the privacy policy |
| Privacy policy | `https://adenclean.onrender.com/policies.html#privacy` |

Service providers that process data on AdenClean's behalf (the server host and the
database host) are not "sharing" under Google's definition; confirm this against Google's
current wording when you fill in the form.

### New personal developer accounts

If your Google Play account is personal and was created after November 13, 2023, Google
requires a closed test with at least 12 testers opted in for 14 days in a row before you
can apply for production access. Organization accounts are exempt. Plan about three weeks
for the first Android launch in that case, and ship iOS first.

## Full description (use on both stores)

AdenClean makes it simple to ask for help cleaning your home.

Send a request in a minute. Choose the kind of cleaning, pick a day and a time of day that suit you, and tell us how to reach you. AdenClean reviews each request and follows up with you.

What you can do
• Request routine home cleaning, a deep clean, or a move-in / move-out clean
• Choose a day and a time of day
• Check the status of every request you have sent
• Once your service is marked complete, leave a private review or report a problem
• Add a request you sent from the AdenClean website

Good to know
• A request is an inquiry, not a confirmed booking. AdenClean talks through the details with you directly.
• AdenClean currently serves Silver Spring, Maryland.
• No account needed. Your requests are saved on your phone.
• Reviews are read privately by AdenClean and are never posted publicly.
• No ads and no tracking.
• Payments are not handled in the app.

Questions? Email applications@adeneats.com or call (240) 342-6088.
