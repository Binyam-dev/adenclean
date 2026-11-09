import type { ConfigContext, ExpoConfig } from 'expo/config';

// app.json holds the fixed settings. This file adds two things:
// - a safety check: a build for the stores must point at the real server over HTTPS, never at localhost;
// - the Stripe payment plugin, only in builds made with EXPO_PUBLIC_MARKETPLACE=1. Version 1 has no
//   payments, so its binary carries no payment SDK (react-native.config.js leaves the native module
//   out of the same builds). The privacy answers in store/LISTING.md assume this.
export default ({ config }: ConfigContext): ExpoConfig => {
  const profile = process.env.EAS_BUILD_PROFILE ?? '';
  const api = process.env.EXPO_PUBLIC_API_URL ?? '';
  const storeBuild = profile === 'production' || profile === 'preview';

  if (storeBuild && !/^https:\/\/[^/]+\.[^/]+/.test(api)) {
    throw new Error(
      `EXPO_PUBLIC_API_URL must be your deployed server's https:// address for the "${profile}" build (got "${api}"). Set it in eas.json under build.${profile}.env.`,
    );
  }
  if (storeBuild && /localhost|127\.0\.0\.1/.test(api)) {
    throw new Error('EXPO_PUBLIC_API_URL points at localhost. Use the deployed server address.');
  }

  if (process.env.EXPO_PUBLIC_MARKETPLACE === '1') {
    return { ...config, plugins: [...(config.plugins ?? []), ['@stripe/stripe-react-native', { enableGooglePay: false }]] } as ExpoConfig;
  }
  return config as ExpoConfig;
};
