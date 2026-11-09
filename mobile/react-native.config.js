// Version 1 of the app has no payments, so builds without EXPO_PUBLIC_MARKETPLACE=1 leave
// Stripe's native module out of the iPhone and Android binaries. That keeps the App Store
// privacy answers and the Play Data safety form accurate: no payment SDK, no payment data.
// Builds with EXPO_PUBLIC_MARKETPLACE=1 include it (app.config.ts adds its config plugin).
const marketplace = process.env.EXPO_PUBLIC_MARKETPLACE === '1';

module.exports = {
  dependencies: marketplace
    ? {}
    : { '@stripe/stripe-react-native': { platforms: { android: null, ios: null } } },
};
