import { useFocusEffect } from 'expo-router';
import * as WebBrowser from 'expo-web-browser';
import { useCallback, useState } from 'react';
import { View } from 'react-native';

import { Notice, StatusPill } from '@/components/Bits';
import { Button } from '@/components/Button';
import { Checkbox, Header } from '@/components/Controls';
import { Field } from '@/components/Field';
import { Screen } from '@/components/Screen';
import { Text } from '@/components/Text';
import { usePalette } from '@/components/use-palette';
import { ApiError } from '@/lib/api';
import { SUPPORT_EMAIL } from '@/lib/config';
import { useSession, refreshUser } from '@/lib/session';
import { longDate, vettingSteps, type StepState } from '@/lib/steps';
import { space } from '@/lib/theme';
import type { PayoutState, Vetting } from '@/lib/v1';

const PILL: Record<StepState, { label: string; tone: 'good' | 'wait' | 'stop' | 'done' }> = {
  done: { label: 'Done', tone: 'good' },
  now: { label: 'Your turn', tone: 'done' },
  waiting: { label: 'Waiting', tone: 'wait' },
  later: { label: 'Later', tone: 'wait' },
  problem: { label: 'Needs attention', tone: 'stop' },
};

/** Apply to clean, sign the background-check disclosure, run both checks, set up payouts. */
export default function CleanerApplication() {
  const p = usePalette();
  const { client, user, token } = useSession();
  const [vetting, setVetting] = useState<Vetting | null | undefined>(undefined);
  const [payout, setPayout] = useState<PayoutState | null>(null);
  const [over18, setOver18] = useState(false);
  const [disclosure, setDisclosure] = useState<string | null>(null);
  const [name, setName] = useState('');
  const [agree, setAgree] = useState(false);
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      const v = await client.vetting();
      setVetting(v);
      if (v?.status === 'approved') {
        void refreshUser();
        setPayout(await client.payoutState());
      }
      setError(null);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : 'Could not load your application.');
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [token]);

  useFocusEffect(useCallback(() => void load(), [load]));

  const run = async (key: string, fn: () => Promise<void>) => {
    setBusy(key);
    setError(null);
    try {
      await fn();
    } catch (e) {
      setError(e instanceof ApiError ? e.message : 'That did not go through. Try again.');
    } finally {
      setBusy(null);
    }
  };

  // The identity and background forms are hosted by Stripe and Checkr, so no ID number or SSN touches this app.
  const openHosted = (key: string, getUrl: () => Promise<string>) =>
    run(key, async () => {
      await WebBrowser.openBrowserAsync(await getUrl());
      await load();
    });

  const showDisclosure = () => run('disclosure', async () => setDisclosure((await client.disclosure()).text));

  const sign = () => run('sign', async () => {
    setVetting(await client.authorizeBackgroundCheck(name));
    setDisclosure(null);
  });

  if (!user) {
    return (
      <Screen>
        <Header title="Clean with AdenClean" />
        <Text tone="soft">Sign in first. Then you can apply.</Text>
      </Screen>
    );
  }

  const steps = vettingSteps(vetting ?? null);
  const signed = !!vetting?.consent_at;
  const action: Record<string, { label: string; onPress: () => void } | undefined> = {
    authorize: vetting && !signed ? { label: 'Read and sign', onPress: () => void showDisclosure() } : undefined,
    identity: signed && ['not_started', 'failed', 'pending'].includes(vetting!.identity_status)
      ? { label: vetting!.identity_status === 'pending' ? 'Reopen the ID check' : 'Verify with Stripe', onPress: () => void openHosted('identity', () => client.identityLink()) } : undefined,
    background: signed && ['not_started', 'invited'].includes(vetting!.background_status)
      ? { label: vetting!.background_status === 'invited' ? 'Reopen the Checkr form' : 'Start with Checkr', onPress: () => void openHosted('background', () => client.backgroundLink()) } : undefined,
  };

  return (
    <Screen>
      <Header title="Clean with AdenClean" />
      {error ? <Notice kind="error">{error}</Notice> : null}

      {vetting === undefined && !error ? <Text tone="soft">Loading…</Text> : null}

      {vetting === null ? (
        <View style={{ gap: space.md }}>
          <Text tone="soft">
            AdenClean checks every cleaner before they can see jobs: your ID, and a background check. You set your own prices and
            choose your jobs. It takes about 10 minutes of your time; the checks themselves take a few days.
          </Text>
          <Checkbox checked={over18} onChange={setOver18}>
            <Text>I am 18 or older.</Text>
          </Checkbox>
          <Button label="Apply" disabled={!over18} loading={busy === 'apply'}
            onPress={() => void run('apply', async () => setVetting(await client.applyToClean()))} testID="cleaner-apply" />
        </View>
      ) : null}

      {vetting && vetting.status === 'denied' ? (
        <Notice kind="error" title="We can't activate your account">
          {`We could not approve this application. If a background check was part of the decision, Checkr sent you a notice with a copy of your report and your rights. Questions: ${SUPPORT_EMAIL}.`}
        </Notice>
      ) : null}

      {vetting && vetting.status === 'pre_adverse' ? (
        <View style={{ gap: space.md }}>
          <Notice kind="error" title="Please read your email">
            {`Checkr sent you a copy of your report and a summary of your rights. If something in it is wrong, you can dispute it${vetting.dispute_deadline ? ` until ${longDate(vetting.dispute_deadline)}` : ''}. We make no final decision until then.`}
          </Notice>
          {vetting.dispute_open ? (
            <Notice kind="info">Your dispute is open. We will review it and email you.</Notice>
          ) : (
            <Button variant="secondary" label="I am disputing my report" loading={busy === 'dispute'}
              onPress={() => void run('dispute', async () => setVetting(await client.disputeDecision()))} />
          )}
        </View>
      ) : null}

      {vetting && !['denied', 'pre_adverse'].includes(vetting.status) ? (
        <View style={{ gap: space.md }}>
          {steps.map((s, i) => (
            <View key={s.id} style={{ gap: space.xs, paddingVertical: space.sm, borderTopWidth: i ? 1 : 0, borderTopColor: p.line }}>
              <View style={{ flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', gap: space.md }}>
                <Text variant="bodyStrong" style={{ flex: 1 }}>{`${i + 1}. ${s.title}`}</Text>
                <StatusPill label={PILL[s.state].label} tone={PILL[s.state].tone} />
              </View>
              <Text tone="soft" variant="small">{s.detail}</Text>
              {action[s.id] && s.state !== 'later' ? (
                <Button variant={s.state === 'now' ? 'primary' : 'secondary'} label={action[s.id]!.label}
                  loading={busy === s.id} onPress={action[s.id]!.onPress} />
              ) : null}
            </View>
          ))}
        </View>
      ) : null}

      {disclosure ? (
        <View style={{ gap: space.md }}>
          <Text variant="heading">Background check disclosure</Text>
          <Text>{disclosure}</Text>
          <Field label="Your full legal name" value={name} onChangeText={setName} autoCapitalize="words"
            hint="Typing your name is your signature." />
          <Checkbox checked={agree} onChange={setAgree}>
            <Text>I have read this and I authorize AdenClean to get a background check on me from Checkr.</Text>
          </Checkbox>
          <Button label="Sign" disabled={!agree || name.trim().length < 3} loading={busy === 'sign'} onPress={() => void sign()} />
        </View>
      ) : null}

      {vetting?.status === 'approved' ? (
        <View style={{ gap: space.md }}>
          <Notice kind="success" title="You are approved">See open jobs under Work.</Notice>
          <Text variant="heading">Get paid</Text>
          {payout === 'off' ? <Text tone="soft">Payouts open soon. We will email you.</Text> : null}
          {payout === 'ready' ? <Notice kind="success">Your payout account is ready. You can send offers.</Notice> : null}
          {payout === 'none' || payout === 'incomplete' ? (
            <>
              <Text tone="soft">
                Add your bank details with Stripe so we can pay you. You need this before you can send an offer.
              </Text>
              <Button label={payout === 'incomplete' ? 'Finish payout setup' : 'Set up payouts'} loading={busy === 'payout'}
                onPress={() => void openHosted('payout', () => client.payoutLink())} testID="payout-setup" />
            </>
          ) : null}
        </View>
      ) : null}
    </Screen>
  );
}
