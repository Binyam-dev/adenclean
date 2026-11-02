import type { ConfigContext, ExpoConfig } from 'expo/config';

// app.json holds the fixed settings. This file adds one safety check: a build for the
// stores must point at the real server over HTTPS, never at localhost.
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

  return config as ExpoConfig;
};
