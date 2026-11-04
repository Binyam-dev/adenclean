import { Pressable, StyleSheet, View } from 'react-native';

import { formatCents, jobStatusLabel, marketServiceTitle, dateRange } from '@/lib/market';
import { radius, space } from '@/lib/theme';
import type { Job } from '@/lib/v1';

import { StatusPill } from './Bits';
import { Text } from './Text';
import { usePalette } from './use-palette';

/** One job in a list. Customers see its status; cleaners see what the job asks for. */
export function JobCard({ job, onPress, showStatus }: { job: Job; onPress: () => void; showStatus: boolean }) {
  const p = usePalette();
  const rooms = `${job.bedrooms} bed · ${job.bathrooms} bath`;
  const money = job.price_cents ? `Booked at ${formatCents(job.price_cents)}` : job.budget_cents ? `Budget ${formatCents(job.budget_cents)}` : 'No budget given';
  const tone = job.status === 'open' ? 'wait' : job.status === 'booked' ? 'good' : job.status === 'completed' ? 'done' : 'stop';
  return (
    <Pressable
      accessibilityRole="button"
      accessibilityLabel={`${marketServiceTitle(job.service_type)}, ${rooms}, ${dateRange(job.date_from, job.date_to)}, ${money}`}
      onPress={onPress}
      style={({ pressed }) => [styles.card, { backgroundColor: p.surface, borderColor: p.line, opacity: pressed ? 0.85 : 1 }]}>
      <View style={styles.top}>
        <Text variant="heading">{marketServiceTitle(job.service_type)}</Text>
        {showStatus ? <StatusPill label={jobStatusLabel(job.status)} tone={tone} /> : null}
      </View>
      <Text tone="soft">
        {rooms} · ZIP {job.zip} · {job.supplies === 'cleaner' ? 'Cleaner brings supplies' : 'Supplies provided'}
      </Text>
      <Text>{dateRange(job.date_from, job.date_to)}</Text>
      <Text variant="bodyStrong">{money}</Text>
    </Pressable>
  );
}

const styles = StyleSheet.create({
  card: { borderRadius: radius.card, borderWidth: 1.5, padding: space.xl, gap: space.sm },
  top: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', gap: space.md },
});
