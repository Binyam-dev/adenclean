# AdenClean mobile app

The native iPhone and Android app for AdenClean, built with Expo (SDK 58) and Expo Router.
It is a customer app with no sign-in: send a cleaning request, follow its status, and
leave a review or report a problem after the service. It talks to the AdenClean server in
the repository root.

- Design notes: [`DESIGN.md`](DESIGN.md)
- Store text, privacy answers and review notes: [`store/LISTING.md`](store/LISTING.md)
- Icons and graphics: `assets/images/` and `store/`

## Run it

```bash
cd mobile
npm install
npm test            # unit tests for validation and the API client
npm run typecheck
npx expo start      # then press i, a, or w
```

The app reads the server address from `EXPO_PUBLIC_API_URL`. For local work, start the
server from the repository root (`ADENCLEAN_STORAGE=memory python main.py`, which saves nothing) and run
`EXPO_PUBLIC_API_URL=http://localhost:5000 npx expo start`. An Android emulator reaches
your computer at `http://10.0.2.2:5000`; a real phone needs your computer's network address.

## Before the first store build

1. **Deploy the server** and note its `https://` address. The repository root has a
   `render.yaml` for Render; see the root README. The server must be reachable over HTTPS
   because both stores' apps must use secure connections.
2. **Put that address in `eas.json`** under `build.preview.env` and `build.production.env`
   (`EXPO_PUBLIC_API_URL`). A build for the stores fails on purpose if this is missing, is
   not `https://`, or points at localhost (see `app.config.ts`).
3. **Confirm the contact details** in `src/lib/config.ts` (support email and phone) match
   what you want customers to use, and that `store/LISTING.md` agrees.
4. **Read the privacy policy** at `static/policies.html` once, as the business owner. It
   describes what the app and website really do, but it is your policy: check the contact
   details and the deletion promise (we delete by hand on request) are what you intend.

## Build and submit with EAS

EAS builds in the cloud, so you do not need a Mac or Android Studio. You need an
[Expo account](https://expo.dev), your Apple Developer account and your Google Play
Developer account. The commands below use `npx eas-cli@latest`; check Expo's current docs
(docs.expo.dev/build and docs.expo.dev/submit) if any prompt differs.

```bash
cd mobile
npx eas-cli@latest login
npx eas-cli@latest init            # links the project; adds the project ID to app.json
```

### Test builds first

```bash
npx eas-cli@latest build --platform android --profile preview   # an .apk you can install
npx eas-cli@latest build --platform ios --profile production    # then send it to TestFlight
```

Install the Android build on a real phone and send a real request to your deployed server.
For iOS, the production build goes to TestFlight (below); there is no installable file for
iPhones outside TestFlight unless you register each device with `eas device:create`.

### iPhone (App Store)

1. In [App Store Connect](https://appstoreconnect.apple.com), create a new app with bundle
   ID `com.adencommunity.clean` (register the identifier first under Certificates,
   Identifiers & Profiles if it is not listed).
2. `npx eas-cli@latest build --platform ios --profile production`. EAS asks you to sign in
   to your Apple account and creates the certificates and profiles for you.
3. `npx eas-cli@latest submit --platform ios --latest`. EAS asks for the App Store Connect
   app it should upload to. The build appears in TestFlight after Apple finishes
   processing it.
4. In App Store Connect, fill in the listing from `store/LISTING.md`, upload
   `store/screenshots/ios-6.9/`, answer App Privacy, add the review notes with a demo link,
   choose the build, and submit for review.

### Android (Google Play)

1. In the [Play Console](https://play.google.com/console), create the app (package
   `com.adencommunity.clean`) and complete the dashboard tasks: store listing, content
   rating, data safety, target audience. Text and graphics are in `store/`.
2. `npx eas-cli@latest build --platform android --profile production` produces an `.aab`
   (the format Google Play wants).
3. Upload the first build by hand in the Play Console (Testing > Internal testing >
   Create release). Google generally requires a new app's first upload to be manual before
   automatic submission can work. After that, `npx eas-cli@latest submit --platform android`
   can upload later builds; it needs a Google service account key, which Expo's docs
   explain how to create.
4. If your Google account is a personal one created after 13 November 2023, run a closed
   test with at least 12 testers for 14 days in a row before you apply for production.
   Organization accounts do not have this step.

## Things that need your attention

- **Server host.** `eas.json` uses `https://adenclean.onrender.com` as a placeholder.
  Replace it with your real address.
- **Demo link for Apple review.** Make a completed demo request and paste its link into the
  review notes (steps are in `store/LISTING.md`). Without it, reviewers cannot see the
  review and problem-report screens.
- **Screenshots come from the web build of the real app,** laid out with captions. They are
  accurate to the UI, but they are not captured on a physical device. Apple accepts this
  style; replace them if you prefer device captures.
- **Not verified on real devices.** The app type-checks, the logic has unit tests, it
  bundles for iOS, Android and web, and the complete flow was run in a browser against the
  real server. It has not been run on a physical iPhone or Android phone. Test builds on
  both before submitting.
- **Notifications are not included.** The server does not send customer emails or push
  notifications, so the app shows status when opened and says so plainly.

## Project layout

```
src/app/            screens (Expo Router): tabs, new request, request detail
src/components/     shared UI: House, Button, Field, Choice, Stars, Screen…
src/lib/            theme, validation, API client, secure storage, status wording
scripts/            asset and screenshot generators
store/              listing text, graphics and screenshots
```
