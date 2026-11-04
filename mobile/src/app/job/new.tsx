import { router } from 'expo-router';
import { useMemo, useState } from 'react';
import { ScrollView, View } from 'react-native';

import { Notice } from '@/components/Bits';
import { Button } from '@/components/Button';
import { Chip, DayChip, OptionCard } from '@/components/Choice';
import { Field } from '@/components/Field';
import { Screen } from '@/components/Screen';
import { Text } from '@/components/Text';
import { ApiError } from '@/lib/api';
import { checkPrice, checkZip, MARKET_SERVICES, parseDollars, type MarketService } from '@/lib/market';
import { useSession } from '@/lib/session';
import { space } from '@/lib/theme';
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

function Counter({ label, value, set, min, max }: { label: string; value: number; set: (n: number) => void; min: number; max: number }) {
  return (
    <View style={{ gap: space.sm }}>
      <Text variant="bodyStrong">{label}</Text>
      <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: space.sm }} accessibilityRole="radiogroup" accessibilityLabel={label}>
        {Array.from({ length: max - min + 1 }, (_, i) => min + i).map((n) => (
          <Chip key={n} label={n === max ? `${n}+` : String(n)} selected={value === n} onPress={() => set(n)} />
        ))}
      </View>
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
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const post = async () => {
    const problem = !service ? 'Choose a type of cleaning.' : checkZip(zip) ?? (!start ? 'Choose a start day.' : null)
      ?? (budget.trim() ? checkPrice(budget) : null);
    if (problem) return setError(problem);
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
      <Text variant="title" accessibilityRole="header">Post a cleaning job</Text>
      <Text tone="soft">Cleaners nearby send you offers with their own price. You choose one, or ask for a better price.</Text>

      <View style={{ gap: space.md }} accessibilityRole="radiogroup" accessibilityLabel="Type of cleaning">
        {MARKET_SERVICES.map((s) => (
          <OptionCard key={s.id} title={s.title} selected={service === s.id} onPress={() => setService(s.id)} />
        ))}
      </View>

      <Field label="ZIP code" value={zip} onChangeText={setZip} keyboardType="number-pad" maxLength={5}
        hint="Your exact address is shared only after you book." autoComplete="postal-code" />
      <Counter label="Bedrooms" value={bedrooms} set={setBedrooms} min={0} max={6} />
      <Counter label="Bathrooms" value={bathrooms} set={setBathrooms} min={1} max={5} />

      <View style={{ gap: space.sm }}>
        <Text variant="bodyStrong">Cleaning supplies</Text>
        <View style={{ flexDirection: 'row', gap: space.sm }} accessibilityRole="radiogroup">
          <Chip label="Cleaner brings them" selected={supplies === 'cleaner'} onPress={() => setSupplies('cleaner')} />
          <Chip label="I have them" selected={supplies === 'customer'} onPress={() => setSupplies('customer')} />
        </View>
      </View>

      <View style={{ gap: space.sm }}>
        <Text variant="bodyStrong">Earliest day</Text>
        <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={{ gap: space.sm }}>
          {days.map((d) => <DayChip key={d.iso} {...d} selected={start === d.iso} onPress={() => setStart(d.iso)} />)}
        </ScrollView>
        <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: space.sm }} accessibilityRole="radiogroup">
          {FLEX.map((f) => <Chip key={f.days} label={f.label} selected={flex === f.days} onPress={() => setFlex(f.days)} />)}
        </View>
      </View>

      <Field label="Your budget" optional hint="Cleaners still name their own price." value={budget}
        onChangeText={setBudget} keyboardType="decimal-pad" />
      <Field label="Notes for the cleaner" optional multiline maxLength={800} value={notes} onChangeText={setNotes}
        hint="For example pets or parking. Don't include health details." counter={`${notes.length} / 800`} />

      {error ? <Notice kind="error">{error}</Notice> : null}
      <Button label="Post job" onPress={() => void post()} loading={busy} testID="job-post" />
      <Button variant="quiet" label="Cancel" onPress={() => router.back()} />
    </Screen>
  );
}
