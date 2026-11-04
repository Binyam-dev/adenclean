import { router } from 'expo-router';
import type { ReactNode } from 'react';
import { useMemo, useState } from 'react';
import { ScrollView, StyleSheet, View } from 'react-native';

import { Notice } from '@/components/Bits';
import { Button } from '@/components/Button';
import { Chip, DayChip, OptionCard } from '@/components/Choice';
import { Header, Stepper } from '@/components/Controls';
import { Field } from '@/components/Field';
import { Screen } from '@/components/Screen';
import { Text } from '@/components/Text';
import { usePalette } from '@/components/use-palette';
import { ApiError } from '@/lib/api';
import { checkPrice, checkZip, MARKET_SERVICES, parseDollars, type MarketService } from '@/lib/market';
import { useSession } from '@/lib/session';
import { radius, space } from '@/lib/theme';
import { dateOptions } from '@/lib/validation';

const FLEX = [
  { days: 0, label: 'That day only' },
  { days: 3, label: 'Within 3 days' },
  { days: 7, label: 'Within a week' },
];

function addDays(iso: string, days: number): string {
  const [y, m, d] = iso.split('-').map(Number);
  const next = new Date(y, m - 1, d + days);
  return `${next.getFullYear()}-${String(next.getMonth() + 1).padStart(2, '0')}-${String(next.getDate()).padStart(2, '0')}`;
}

/** A titled group of related questions, so the form reads as four short steps. */
function Section({ step, title, error, children }: { step: number; title: string; error?: string | null; children: ReactNode }) {
  const p = usePalette();
  return (
    <View style={[styles.section, { backgroundColor: p.surface, borderColor: error ? p.error : p.line }]}>
      <Text variant="caption" tone="soft">STEP {step} OF 4</Text>
      <Text variant="heading" accessibilityRole="header">{title}</Text>
      {children}
      {error ? <Text variant="small" tone="error" accessibilityLiveRegion="polite">{error}</Text> : null}
    </View>
  );
}

export default function NewJob() {
  const { client } = useSession();
  const days = useMemo(() => dateOptions(new Date(), 21), []);
  const [service, setService] = useState<MarketService | null>(null);
  const [zip, setZip] = useState('');
  const [bedrooms, setBedrooms] = useState(2);
  const [bathrooms, setBathrooms] = useState(1);
  const [supplies, setSupplies] = useState<'customer' | 'cleaner'>('cleaner');
  const [start, setStart] = useState<string | null>(null);
  const [flex, setFlex] = useState(3);
  const [budget, setBudget] = useState('');
  const [notes, setNotes] = useState('');
  const [tried, setTried] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const errors = {
    service: service ? null : 'Choose a type of cleaning.',
    zip: checkZip(zip),
    start: start ? null : 'Choose the earliest day that works.',
    budget: budget.trim() ? checkPrice(budget) : null,
  };
  const valid = !Object.values(errors).some(Boolean);

  const post = async () => {
    setTried(true);
    if (!valid) return setError('Check the highlighted steps.');
    setBusy(true);
    setError(null);
    try {
      const job = await client.createJob({
        serviceType: service!, zip: zip.trim(), bedrooms, bathrooms, supplies,
        dateFrom: start!, dateTo: addDays(start!, flex),
        budgetCents: budget.trim() ? parseDollars(budget)! : undefined, notes: notes.trim(),
      });
      router.replace(`/job/${job.id}`);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : 'Could not post the job. Try again.');
    } finally {
      setBusy(false);
    }
  };

  return (
    <Screen>
      <Header title="Post a cleaning job" />
      <Text tone="soft">Cleaners nearby send offers with their own price. You choose one, or suggest a different price.</Text>

      <Section step={1} title="What needs cleaning?" error={tried ? errors.service : null}>
        <View style={{ gap: space.sm }} accessibilityRole="radiogroup" accessibilityLabel="Type of cleaning">
          {MARKET_SERVICES.map((s) => (
            <OptionCard key={s.id} title={s.title} selected={service === s.id} onPress={() => setService(s.id)} />
          ))}
        </View>
      </Section>

      <Section step={2} title="Where, and how big?">
        <Field label="ZIP code" value={zip} onChangeText={setZip} keyboardType="number-pad" maxLength={5}
          hint="Your street address is shared only with the cleaner you book." autoComplete="postal-code"
          error={errors.zip} showError={tried} />
        <Stepper label="Bedrooms" value={bedrooms} onChange={setBedrooms} min={0} max={8} />
        <Stepper label="Bathrooms" value={bathrooms} onChange={setBathrooms} min={1} max={6} />
        <Text variant="bodyStrong">Cleaning supplies</Text>
        <View style={styles.row} accessibilityRole="radiogroup" accessibilityLabel="Cleaning supplies">
          <Chip label="Cleaner brings them" selected={supplies === 'cleaner'} onPress={() => setSupplies('cleaner')} />
          <Chip label="I have them" selected={supplies === 'customer'} onPress={() => setSupplies('customer')} />
        </View>
      </Section>

      <Section step={3} title="When?" error={tried ? errors.start : null}>
        <Text variant="bodyStrong">Earliest day</Text>
        <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={{ gap: space.sm }}
          accessibilityRole="radiogroup" accessibilityLabel="Earliest day">
          {days.map((d) => <DayChip key={d.iso} {...d} selected={start === d.iso} onPress={() => setStart(d.iso)} />)}
        </ScrollView>
        <Text variant="bodyStrong">How flexible?</Text>
        <View style={styles.row} accessibilityRole="radiogroup" accessibilityLabel="How flexible">
          {FLEX.map((f) => <Chip key={f.days} label={f.label} selected={flex === f.days} onPress={() => setFlex(f.days)} />)}
        </View>
      </Section>

      <Section step={4} title="Anything else?">
        <Field label="Your budget" optional placeholder="$ 120" hint="A guide only. Cleaners still name their own price."
          value={budget} onChangeText={setBudget} keyboardType="decimal-pad" error={errors.budget} showError={tried || !!budget} />
        <Field label="Notes for the cleaner" optional multiline maxLength={800} value={notes} onChangeText={setNotes}
          hint="Pets, parking, rooms to skip. Don't include health details." counter={`${notes.length} / 800`} />
      </Section>

      {error ? <Notice kind="error">{error}</Notice> : null}
      <Button label="Post job" onPress={() => void post()} loading={busy} testID="job-post" />
      <Text variant="small" tone="soft" style={{ textAlign: 'center' }}>
        Posting is free. You only book when you accept an offer.
      </Text>
    </Screen>
  );
}

const styles = StyleSheet.create({
  section: { borderRadius: radius.card, borderWidth: 1.5, padding: space.xl, gap: space.md },
  row: { flexDirection: 'row', flexWrap: 'wrap', gap: space.sm },
});
