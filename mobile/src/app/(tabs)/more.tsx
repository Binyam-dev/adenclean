import Constants from 'expo-constants';
import * as WebBrowser from 'expo-web-browser';
import { useState } from 'react';
import { Linking, Pressable, StyleSheet, View } from 'react-native';

import { Notice, Rule } from '@/components/Bits';
import { Screen } from '@/components/Screen';
import { Text } from '@/components/Text';
import { usePalette } from '@/components/use-palette';
import { PRIVACY_URL, SERVICE_AREA, SUPPORT_EMAIL, SUPPORT_PHONE_DISPLAY, SUPPORT_PHONE_LINK, TERMS_URL } from '@/lib/config';
import { confirmAction } from '@/lib/confirm';
import { router } from 'expo-router';

import { ApiError } from '@/lib/api';
import { MARKET_ENABLED } from '@/lib/market';
import { signOut, useSession } from '@/lib/session';
import { clearAll } from '@/lib/storage';
import { radius, space } from '@/lib/theme';

function Row({ title, detail, onPress, tone = 'ink' }: { title: string; detail?: string; onPress: () => void; tone?: 'ink' | 'error' }) {
  return (
    <Pressable
      accessibilityRole="button"
      accessibilityLabel={detail ? `${title}. ${detail}` : title}
      onPress={onPress}
      style={({ pressed }) => [styles.row, { opacity: pressed ? 0.6 : 1 }]}>
      <Text variant="bodyStrong" tone={tone}>
        {title}
      </Text>
      {detail ? (
        <Text variant="small" tone="soft">
          {detail}
        </Text>
      ) : null}
    </Pressable>
  );
}

export default function More() {
  const p = usePalette();
  const [done, setDone] = useState(false);
  const [accountError, setAccountError] = useState<string | null>(null);
  const { user, client } = useSession();
  const version = Constants.expoConfig?.version ?? '1.0.0';

  const deleteAccount = async () => {
    const yes = await confirmAction({
      title: 'Delete your account?',
      message:
        'Your account, profile and open jobs and offers are removed. Booked jobs, payment records and safety reports are kept as the law requires. This cannot be undone.',
      confirmLabel: 'Delete account',
      cancelLabel: 'Keep account',
      destructive: true,
    });
    if (!yes) return;
    try {
      await client.deleteAccount();
      await signOut();
    } catch (e) {
      setAccountError(e instanceof ApiError ? e.message : 'Could not delete the account. Try again.');
    }
  };

  const removeSaved = async () => {
    const yes = await confirmAction({
      title: 'Remove saved requests?',
      message:
        "This removes your requests from this phone, so you can't check their status or leave feedback here anymore. AdenClean keeps the requests you already sent.",
      confirmLabel: 'Remove requests',
      cancelLabel: 'Keep requests',
      destructive: true,
    });
    if (!yes) return;
    await clearAll();
    setDone(true);
  };

  return (
    <Screen>
      <Text variant="title" accessibilityRole="header">
        More
      </Text>

      <View style={[styles.group, { backgroundColor: p.surface, borderColor: p.line }]}>
        <Text variant="heading">About AdenClean</Text>
        <Text variant="body" tone="soft">
          AdenClean brings households and cleaning services together in a way that feels dependable, personal and easy to understand. Now serving {SERVICE_AREA}.
        </Text>
      </View>

      {MARKET_ENABLED ? (
        <View style={[styles.group, { backgroundColor: p.surface, borderColor: p.line }]}>
          <Text variant="heading">Your account</Text>
          {user ? (
            <>
              <Text>{user.displayName}</Text>
              <Text tone="soft">{user.email}</Text>
              <Rule />
              <Row title="Blocked people" detail="See who you blocked, or unblock someone" onPress={() => router.push('/blocked')} />
              <Rule />
              <Row title="Sign out" onPress={() => void signOut()} />
              <Rule />
              <Row title="Delete my account" detail="Removes your account and open jobs from AdenClean" tone="error"
                onPress={() => void deleteAccount()} />
            </>
          ) : (
            <Row title="Sign in or create an account" detail="Hire cleaners or find cleaning work" onPress={() => router.push('/sign-in')} />
          )}
          {accountError ? <Notice kind="error">{accountError}</Notice> : null}
        </View>
      ) : null}

      <View style={[styles.group, { backgroundColor: p.surface, borderColor: p.line }]}>
        <Text variant="heading">Get in touch</Text>
        <Row title="Email AdenClean" detail={SUPPORT_EMAIL} onPress={() => void Linking.openURL(`mailto:${SUPPORT_EMAIL}`)} />
        <Rule />
        <Row title="Call AdenClean" detail={SUPPORT_PHONE_DISPLAY} onPress={() => void Linking.openURL(SUPPORT_PHONE_LINK)} />
      </View>

      <View style={[styles.group, { backgroundColor: p.surface, borderColor: p.line }]}>
        <Text variant="heading">Your information</Text>
        <Row title="Privacy policy" detail="What we collect and how it is used" onPress={() => void WebBrowser.openBrowserAsync(PRIVACY_URL)} />
        <Rule />
        <Row title="Service terms" detail="What a request does and does not mean" onPress={() => void WebBrowser.openBrowserAsync(TERMS_URL)} />
        <Rule />
        <Row
          title="Ask AdenClean to delete my information"
          detail="Opens an email with your request ready to send"
          onPress={() =>
            void Linking.openURL(
              `mailto:${SUPPORT_EMAIL}?subject=${encodeURIComponent('Delete my AdenClean information')}&body=${encodeURIComponent(
                'Please delete the information I sent through the AdenClean app.\n\nRequest reference (shown in the app, if you have it): ',
              )}`,
            )
          }
        />
        <Rule />
        <Row title="Remove saved requests from this phone" detail="Doesn't delete anything AdenClean already has" tone="error" onPress={() => void removeSaved()} />
      </View>

      {done ? <Notice kind="success" title="Saved requests removed">Nothing is saved on this phone now.</Notice> : null}

      <Text variant="caption" tone="soft">
        Version {version}
      </Text>
    </Screen>
  );
}

const styles = StyleSheet.create({
  group: { borderRadius: radius.card, borderWidth: 1.5, padding: space.xl, gap: space.md },
  row: { minHeight: 48, justifyContent: 'center', gap: 2, paddingVertical: 4 },
});
