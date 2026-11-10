# Store requirements checked on 2026-11-09

Checked on the official Apple, Google and Expo pages. "Unverified" means the official page does not say it outright.

| # | Requirement | Source | What AdenClean does |
| --- | --- | --- | --- |
| 1 | Google Play: new apps and updates must target Android 16 (API 36). Expo SDK 58 builds target 36. | support.google.com/googleplay/android-developer/answer/11926878; docs.expo.dev/versions/latest | Keep SDK 58 defaults. |
| 2 | Google Play: 16 KB page-size support is required for updates from 2027-02-01. Unverified that every SDK 58 native library is aligned. | developer.android.com/guide/practices/page-sizes | Check the 16 KB status of the AAB in Play Console after upload. |
| 3 | Google Play personal accounts created after 2023-11-13: closed test with at least 12 testers opted in for 14 days, then apply for production. | support.google.com/googleplay/android-developer/answer/14151465 | Owner recruits testers. About 3 weeks. |
| 4 | Data safety: declare Name, Email address, Other user-generated content as collected, not shared, for app functionality, encrypted in transit. Declare Approximate location to be safe (typed town or ZIP; unverified). No deletion URL needed without accounts. | answer/10787469; answer/13327111 | Answers are in `mobile/store/LISTING.md`. |
| 5 | Apple: uploads must be built with Xcode 26+ and the iOS 26 SDK. Expo SDK 58 needs Xcode 26.4+. | developer.apple.com/news/upcoming-requirements | Use the default EAS image; confirm Xcode in the build log. |
| 6 | Apple privacy manifest: required-reason APIs must be declared. Expo packages ship manifests, but static pods are not always parsed, so declare reasons in `expo.ios.privacyManifests`. | docs.expo.dev/guides/apple-privacy | Declared in `app.json`. |
| 7 | Apple privacy label: Contact Info (Name, Email), User Content (Customer Support, Other User Content), linked to the user, app functionality, no tracking. Coarse Location declared conservatively for the typed town or ZIP (unverified). | developer.apple.com/app-store/app-privacy-details | Answers are in `mobile/store/LISTING.md`. |
| 8 | Guideline 1.2 (user-generated content) is written for content posted to the app or other users. No explicit exemption for private feedback (unverified inference that it does not apply). | developer.apple.com/app-store/review/guidelines | Review notes say reviews go only to the business and are never displayed. |
| 9 | Guideline 5.1.1(v): in-app account deletion is required only if the app supports account creation. | same | v1 has no accounts. The deletion-request route is in the privacy policy and the More tab. |
| 10 | Apple screenshots: at least one set for iPhone with Dynamic Island, 1206x2622 or 1179x2556; also supply 1320x2868. iPad only if the app runs on iPad. | developer.apple.com/help/app-store-connect/reference/app-information/screenshot-specifications | `supportsTablet` is false. Both sets are in `mobile/store/screenshots`. |
| 11 | Google screenshots: 2 to 8 per device type, at least 4 at 1080x1920 or larger to be eligible for recommendations; icon 512x512; feature graphic 1024x500. | support.google.com/googleplay/android-developer/answer/9866151 | In `mobile/store`. |
| 12 | Age rating: Apple questionnaire (tiers 4+, 9+, 13+, 16+, 18+); all "None" gives 4+. Google IARC questionnaire; expected Everyone (unverified). | Apple age-ratings reference; answer/9859655 | Answer "no" or "none" throughout. |
| 13 | Export compliance: HTTPS only is exempt. `ITSAppUsesNonExemptEncryption` is false. | developer.apple.com/documentation/security/complying-with-encryption-export-regulations | Set in `app.json`. |
| 14 | Sentry in the app would add Crash Data, Performance Data and Other Diagnostic Data to both privacy forms, plus three required-reason APIs. | docs.sentry.io/platforms/react-native/data-management | Not added to the app in v1 (see DECISIONS.md). Server errors are monitored on the server. |
