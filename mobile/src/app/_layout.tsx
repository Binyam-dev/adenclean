import {
  BricolageGrotesque_700Bold,
  BricolageGrotesque_800ExtraBold,
} from '@expo-google-fonts/bricolage-grotesque';
import { Figtree_400Regular, Figtree_500Medium, Figtree_600SemiBold } from '@expo-google-fonts/figtree';
import { useFonts } from 'expo-font';
import { Stack } from 'expo-router';
import * as SplashScreen from 'expo-splash-screen';
import { StatusBar } from 'expo-status-bar';
import { useEffect } from 'react';

import { usePalette } from '@/components/use-palette';
import { MARKET_ENABLED } from '@/lib/market';

void SplashScreen.preventAutoHideAsync();

export default function RootLayout() {
  const p = usePalette();
  const [loaded, error] = useFonts({
    BricolageGrotesque_700Bold,
    BricolageGrotesque_800ExtraBold,
    Figtree_400Regular,
    Figtree_500Medium,
    Figtree_600SemiBold,
  });

  useEffect(() => {
    if (loaded || error) void SplashScreen.hideAsync();
  }, [loaded, error]);

  // Wait for the fonts so text never flashes in the wrong typeface.
  if (!loaded && !error) return null;

  return (
    <>
      <StatusBar style={p.bg === '#0F1F1A' ? 'light' : 'dark'} />
      <Stack screenOptions={{ headerShown: false, contentStyle: { backgroundColor: p.bg } }}>
        <Stack.Screen name="(tabs)" />
        <Stack.Screen name="new" options={{ presentation: 'fullScreenModal', animation: 'slide_from_bottom' }} />
        <Stack.Screen name="request/[ref]" />
        {/* Marketplace screens exist only in builds made with EXPO_PUBLIC_MARKETPLACE=1. In a
            version 1 build a link to them goes nowhere, so no sign-in or payment screen can be reached. */}
        <Stack.Protected guard={MARKET_ENABLED}>
          <Stack.Screen name="sign-in" options={{ presentation: 'modal' }} />
          <Stack.Screen name="job/new" options={{ presentation: 'fullScreenModal', animation: 'slide_from_bottom' }} />
          <Stack.Screen name="job/[id]" />
          <Stack.Screen name="cleaner" />
          <Stack.Screen name="blocked" />
        </Stack.Protected>
      </Stack>
    </>
  );
}
