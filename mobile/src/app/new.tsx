import * as Haptics from 'expo-haptics';
import { router, useLocalSearchParams } from 'expo-router';
import * as WebBrowser from 'expo-web-browser';
import { useMemo, useState } from 'react';
import { KeyboardAvoidingView, Platform, Pressable, ScrollView, StyleSheet, View } from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';

import { Notice, Rule } from '@/components/Bits';
import { Button } from '@/components/Button';
import { Chip, DayChip, OptionCard } from '@/components/Choice';
import { Field } from '@/components/Field';
import { House } from '@/components/House';
import { Screen } from '@/components/Screen';
import { Text } from '@/components/Text';
import { usePalette } from '@/components/use-palette';
import { ApiError, sendRequest, type SentRequest } from '@/lib/api';
import { PRIVACY_URL, TERMS_URL } from '@/lib/config';
import { confirmAction } from '@/lib/confirm';
import { saveRequest, type SavedRequest } from '@/lib/storage';
import { keepSent, sendAndKeep } from '@/lib/submit';
import { MAX_WIDTH, radius, space } from '@/lib/theme';
import {
  SERVICES,
  TIMES,
  clean,
  dateOptions,
  detailErrors,
  emptyDraft,
  isReady,
  serviceTitle,
  speakDate,
  stepsComplete,
  timeTitle,
  type RequestDraft,
  type ServiceId,
} from '@/lib/validation';

const TITLES = ['What needs cleaning?', 'When works for you?', 'How can we reach you?', 'Check and send'];

export default function NewRequest() {
  const p = usePalette();
  const insets = useSafeAreaInsets();
  const params = useLocalSearchParams<{ service?: string }>();
  const first = SERVICES.find((s) => s.id === params.service)?.id ?? null;

  const [draft, setDraft] = useState<RequestDraft>({ ...emptyDraft, service: first });
  const [step, setStep] = useState(0);
  const [showErrors, setShowErrors] = useState(false);
  const [sending, setSending] = useState(false);
  const [error, setError] = useState<string | null>(null);
  // Set when the server accepted the request but the phone couldn't save it. From then on
  // the button retries the save and never sends the request again.
  const [unsaved, setUnsaved] = useState<{ sent: SentRequest; item: SavedRequest } | null>(null);

  const days = useMemo(() => dateOptions(new Date()), []);
  const done = stepsComplete(draft);
  const lit = [done.service, done.when, done.details, done.review];
  const errors = detailErrors(draft);
  const dirty = draft.name !== '' || draft.email !== '' || draft.area !== '' || draft.notes !== '' || draft.date !== null || draft.time !== null || (draft.service !== null && draft.service !== first);

  const set = <K extends keyof RequestDraft>(key: K, value: RequestDraft[K]) => setDraft((d) => ({ ...d, [key]: value }));

  const close = async () => {
    if (unsaved) {
      const leave = await confirmAction({
        title: 'Leave without saving?',
        message: `Your request ${unsaved.sent.reference} was sent, but it isn't saved on this phone. Copy the private code first so you can add it under Requests later.`,
        confirmLabel: 'Leave',
        cancelLabel: 'Stay',
        destructive: true,
      });
      if (!leave) return;
    } else if (dirty) {
      const discard = await confirmAction({
        title: 'Discard this request?',
        message: "What you've entered won't be saved.",
        confirmLabel: 'Discard request',
        cancelLabel: 'Keep editing',
        destructive: true,
      });
      if (!discard) return;
    }
    router.back();
  };

  const next = async () => {
    setError(null);
    if (step === 0 && !done.service) return;
    if (step === 1 && !done.when) return;
    if (step === 2 && !done.details) {
      setShowErrors(true);
      return;
    }
    if (step < 3) {
      setStep(step + 1);
      return;
    }
    const finish = (sent: SentRequest) => {
      if (Platform.OS !== 'web') void Haptics.notificationAsync(Haptics.NotificationFeedbackType.Success);
      router.replace({ pathname: '/request/[ref]', params: { ref: sent.reference, sent: '1' } });
    };

    setSending(true);
    if (unsaved) {
      // Already on the server: only retry keeping it on the phone.
      if (await keepSent(unsaved.item, { save: saveRequest })) {
        finish(unsaved.sent);
        return;
      }
      setSending(false);
      return;
    }

    if (!isReady(draft)) {
      setSending(false);
      return;
    }
    const describe = (sent: SentRequest): SavedRequest => ({
      reference: sent.reference,
      token: sent.token,
      createdAt: new Date().toISOString(),
      service: draft.service as string,
      date: draft.date as string,
      time: draft.time as string,
    });
    try {
      const outcome = await sendAndKeep(() => sendRequest(draft), describe, { save: saveRequest });
      if (outcome.saved) {
        finish(outcome.sent);
        return;
      }
      setUnsaved({ sent: outcome.sent, item: describe(outcome.sent) });
      setSending(false);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "We couldn't send your request. Try again in a moment.");
      setSending(false);
    }
  };

  const nextLabel = unsaved ? 'Try saving again' : step === 3 ? 'Send request' : 'Continue';
  const canContinue = unsaved ? true : step === 0 ? done.service : step === 1 ? done.when : step === 3 ? done.review : true;

  return (
    <View style={{ flex: 1, backgroundColor: p.bg }}>
      <KeyboardAvoidingView style={{ flex: 1 }} behavior={Platform.OS === 'ios' ? 'padding' : undefined}>
        <Screen bottomInset={96}>
          <View style={styles.top}>
            <Pressable
              accessibilityRole="button"
              accessibilityLabel="Close and leave this request"
              onPress={() => void close()}
              style={styles.close}>
              <Text variant="bodyStrong" tone="primary">
                Close
              </Text>
            </Pressable>
            <Text variant="caption" tone="soft" accessibilityLabel={`Step ${step + 1} of 4`}>
              Step {step + 1} of 4
            </Text>
          </View>

          <View style={styles.head}>
            <House lit={lit} size={112} />
            <View style={styles.headText}>
              <Text variant="title" accessibilityRole="header">
                {TITLES[step]}
              </Text>
            </View>
          </View>

          {step === 0 ? (
            <View style={styles.stack} accessibilityRole="radiogroup">
              {SERVICES.map((service) => (
                <OptionCard
                  key={service.id}
                  title={service.title}
                  detail={service.description}
                  selected={draft.service === service.id}
                  onPress={() => set('service', service.id as ServiceId)}
                />
              ))}
            </View>
          ) : null}

          {step === 1 ? (
            <View style={styles.stack}>
              <Text variant="bodyStrong">Day</Text>
              <ScrollView
                horizontal
                showsHorizontalScrollIndicator={false}
                contentContainerStyle={styles.days}
                accessibilityRole="radiogroup"
                accessibilityLabel="Choose a day">
                {days.map((day) => (
                  <DayChip key={day.iso} {...day} selected={draft.date === day.iso} onPress={() => set('date', day.iso)} />
                ))}
              </ScrollView>
              <Text variant="bodyStrong" style={{ marginTop: space.sm }}>
                Time of day
              </Text>
              <View style={styles.chips} accessibilityRole="radiogroup" accessibilityLabel="Choose a time of day">
                {TIMES.map((time) => (
                  <Chip key={time.id} label={time.title} selected={draft.time === time.id} onPress={() => set('time', time.id)} />
                ))}
              </View>
              <Text variant="small" tone="soft">
                This is when you&apos;d like help. AdenClean talks through the exact timing with you.
              </Text>
            </View>
          ) : null}

          {step === 2 ? (
            <View style={styles.stack}>
              <Field
                label="Full name"
                value={draft.name}
                onChangeText={(v) => set('name', v)}
                error={errors.name}
                showError={showErrors}
                autoComplete="name"
                textContentType="name"
                returnKeyType="next"
                maxLength={120}
              />
              <Field
                label="Email address"
                value={draft.email}
                onChangeText={(v) => set('email', v)}
                error={errors.email}
                showError={showErrors}
                keyboardType="email-address"
                autoCapitalize="none"
                autoComplete="email"
                textContentType="emailAddress"
                returnKeyType="next"
                maxLength={260}
              />
              <Field
                label="Town or ZIP code"
                hint="Please leave out street addresses and door codes."
                value={draft.area}
                onChangeText={(v) => set('area', v)}
                error={errors.area}
                showError={showErrors}
                autoComplete="postal-code"
                returnKeyType="next"
                maxLength={120}
              />
              <Field
                label="Anything else we should know?"
                optional
                multiline
                value={draft.notes}
                onChangeText={(v) => set('notes', v)}
                error={errors.notes}
                showError={showErrors}
                counter={`${clean(draft.notes, true).length} of 800`}
                hint="No entry codes or payment details."
                maxLength={900}
              />
            </View>
          ) : null}

          {step === 3 ? (
            <View style={styles.stack}>
              <View style={[styles.summary, { backgroundColor: p.surface, borderColor: p.line }]}>
                <SummaryRow label="Service" value={draft.service ? serviceTitle(draft.service) : ''} onChange={() => setStep(0)} />
                <Rule />
                <SummaryRow
                  label="When"
                  value={draft.date && draft.time ? `${speakDate(draft.date)}, ${timeTitle(draft.time).toLowerCase()}` : ''}
                  onChange={() => setStep(1)}
                />
                <Rule />
                <SummaryRow
                  label="You"
                  value={`${clean(draft.name)}\n${clean(draft.email).toLowerCase()}\n${clean(draft.area)}`}
                  onChange={() => setStep(2)}
                />
                {clean(draft.notes, true) ? (
                  <>
                    <Rule />
                    <SummaryRow label="Notes" value={clean(draft.notes, true)} onChange={() => setStep(2)} />
                  </>
                ) : null}
              </View>

              <Pressable
                accessibilityRole="checkbox"
                accessibilityState={{ checked: draft.consent }}
                accessibilityLabel="I agree to AdenClean saving these details to review my request. I understand it is not a confirmed booking."
                onPress={() => set('consent', !draft.consent)}
                style={styles.consent}>
                <View
                  style={[
                    styles.box,
                    { borderColor: draft.consent ? p.primary : p.inkSoft, backgroundColor: draft.consent ? p.primary : 'transparent' },
                  ]}>
                  {draft.consent ? (
                    <Text variant="bodyStrong" tone="onPrimary" style={{ lineHeight: 20 }}>
                      ✓
                    </Text>
                  ) : null}
                </View>
                <Text variant="body" style={{ flex: 1 }}>
                  I agree to AdenClean saving these details to review my request. I understand it isn&apos;t a confirmed booking.
                </Text>
              </Pressable>

              <View style={styles.links}>
                <Button label="Privacy policy" variant="quiet" onPress={() => void WebBrowser.openBrowserAsync(PRIVACY_URL)} />
                <Button label="Service terms" variant="quiet" onPress={() => void WebBrowser.openBrowserAsync(TERMS_URL)} />
              </View>

              {unsaved ? (
                <View style={styles.stack}>
                  <Notice kind="success" title={`Request ${unsaved.sent.reference} was sent`}>
                    {"AdenClean has your request, but we couldn't save it on this phone. Don't send it again. Try saving again, or copy your private code below and add it under Requests later."}
                  </Notice>
                  <Text variant="small" tone="soft">
                    Private code
                  </Text>
                  <Text variant="bodyStrong" selectable accessibilityLabel="Private code, selectable">
                    {unsaved.sent.token}
                  </Text>
                </View>
              ) : error ? (
                <Notice kind="error" title="Your request wasn't sent">
                  {error}
                </Notice>
              ) : null}
            </View>
          ) : null}
        </Screen>

        <View
          style={[
            styles.bar,
            { backgroundColor: p.bg, borderTopColor: p.line, paddingBottom: Math.max(insets.bottom, space.lg) },
          ]}>
          <View style={styles.barInner}>
            {step > 0 && !unsaved ? (
              <View style={{ flex: 1 }}>
                <Button label="Back" variant="secondary" onPress={() => setStep(step - 1)} disabled={sending} />
              </View>
            ) : null}
            <View style={{ flex: 2 }}>
              <Button label={nextLabel} onPress={() => void next()} disabled={!canContinue} loading={sending} />
            </View>
          </View>
        </View>
      </KeyboardAvoidingView>
    </View>
  );
}

function SummaryRow({ label, value, onChange }: { label: string; value: string; onChange: () => void }) {
  return (
    <View style={styles.summaryRow}>
      <View style={{ flex: 1, gap: 2 }}>
        <Text variant="caption" tone="soft">
          {label}
        </Text>
        <Text variant="body">{value}</Text>
      </View>
      <Pressable
        accessibilityRole="button"
        accessibilityLabel={`Change ${label.toLowerCase()}`}
        onPress={onChange}
        style={styles.change}>
        <Text variant="bodyStrong" tone="primary">
          Change
        </Text>
      </Pressable>
    </View>
  );
}

const styles = StyleSheet.create({
  top: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between' },
  close: { minHeight: 48, minWidth: 48, justifyContent: 'center' },
  head: { flexDirection: 'row', alignItems: 'center', gap: space.lg },
  headText: { flex: 1 },
  stack: { gap: space.md },
  days: { gap: space.sm + 2, paddingRight: space.xl },
  chips: { flexDirection: 'row', flexWrap: 'wrap', gap: space.sm + 2 },
  summary: { borderRadius: radius.card, borderWidth: 1.5, paddingHorizontal: space.xl, paddingVertical: space.sm },
  summaryRow: { flexDirection: 'row', alignItems: 'center', gap: space.md, paddingVertical: space.md },
  change: { minHeight: 48, minWidth: 64, alignItems: 'flex-end', justifyContent: 'center' },
  consent: { flexDirection: 'row', gap: space.md, alignItems: 'flex-start', minHeight: 48, paddingVertical: space.sm },
  box: { width: 28, height: 28, borderRadius: 8, borderWidth: 2, alignItems: 'center', justifyContent: 'center', marginTop: 2 },
  links: { flexDirection: 'row', gap: space.sm, flexWrap: 'wrap' },
  bar: { borderTopWidth: StyleSheet.hairlineWidth * 2, paddingTop: space.md, alignItems: 'center' },
  barInner: { width: '100%', maxWidth: MAX_WIDTH, paddingHorizontal: space.xl, flexDirection: 'row', gap: space.md },
});
