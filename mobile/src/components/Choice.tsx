import * as Haptics from 'expo-haptics';
import { Platform, Pressable, StyleSheet, View } from 'react-native';

import { MIN_TOUCH, radius, space } from '@/lib/theme';

import { Text } from './Text';
import { usePalette } from './use-palette';

function tap() {
  if (Platform.OS !== 'web') void Haptics.selectionAsync();
}

/** A large selectable row, for choices with a title and a line of explanation. */
export function OptionCard({
  title,
  detail,
  selected,
  onPress,
}: {
  title: string;
  detail?: string;
  selected: boolean;
  onPress: () => void;
}) {
  const p = usePalette();
  return (
    <Pressable
      accessibilityRole="radio"
      accessibilityState={{ checked: selected }}
      accessibilityLabel={detail ? `${title}. ${detail}` : title}
      onPress={() => {
        tap();
        onPress();
      }}
      style={({ pressed }) => [
        styles.card,
        {
          backgroundColor: selected ? p.primary : p.surface,
          borderColor: selected ? p.primary : p.line,
          opacity: pressed ? 0.9 : 1,
        },
      ]}>
      <View style={styles.cardText}>
        <Text variant="heading" style={{ color: selected ? p.onPrimary : p.ink }}>
          {title}
        </Text>
        {detail ? (
          <Text variant="small" style={{ color: selected ? p.onPrimary : p.inkSoft, opacity: selected ? 0.9 : 1 }}>
            {detail}
          </Text>
        ) : null}
      </View>
      <View style={[styles.dot, { borderColor: selected ? p.accent : p.inkSoft, backgroundColor: selected ? p.accent : 'transparent' }]}>
        {selected ? <View style={[styles.dotInner, { backgroundColor: p.onAccent }]} /> : null}
      </View>
    </Pressable>
  );
}

/** A compact selectable pill, for short choices like a time of day. */
export function Chip({ label, selected, onPress }: { label: string; selected: boolean; onPress: () => void }) {
  const p = usePalette();
  return (
    <Pressable
      accessibilityRole="radio"
      accessibilityState={{ checked: selected }}
      accessibilityLabel={label}
      onPress={() => {
        tap();
        onPress();
      }}
      style={({ pressed }) => [
        styles.chip,
        {
          backgroundColor: selected ? p.primary : 'transparent',
          borderColor: selected ? p.primary : p.line,
          opacity: pressed ? 0.85 : 1,
        },
      ]}>
      <Text variant="bodyStrong" style={{ color: selected ? p.onPrimary : p.ink }}>
        {label}
      </Text>
    </Pressable>
  );
}

/** A day in the date strip: weekday on top, number large, month below. */
export function DayChip({
  weekday,
  day,
  month,
  spoken,
  selected,
  onPress,
}: {
  weekday: string;
  day: string;
  month: string;
  spoken: string;
  selected: boolean;
  onPress: () => void;
}) {
  const p = usePalette();
  const fg = selected ? p.onPrimary : p.ink;
  return (
    <Pressable
      accessibilityRole="radio"
      accessibilityState={{ checked: selected }}
      accessibilityLabel={spoken}
      onPress={() => {
        tap();
        onPress();
      }}
      style={({ pressed }) => [
        styles.day,
        {
          backgroundColor: selected ? p.primary : p.surface,
          borderColor: selected ? p.primary : p.line,
          opacity: pressed ? 0.85 : 1,
        },
      ]}>
      <Text variant="caption" style={{ color: fg, opacity: 0.8 }}>
        {weekday}
      </Text>
      <Text variant="title" style={{ color: fg, fontSize: 24, lineHeight: 28 }}>
        {day}
      </Text>
      <Text variant="caption" style={{ color: fg, opacity: 0.8 }}>
        {month}
      </Text>
    </Pressable>
  );
}

const styles = StyleSheet.create({
  card: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: space.lg,
    minHeight: 76,
    borderRadius: radius.card,
    borderWidth: 1.5,
    paddingHorizontal: space.xl,
    paddingVertical: space.lg,
  },
  cardText: { flex: 1, gap: 4 },
  dot: { width: 26, height: 26, borderRadius: 13, borderWidth: 2, alignItems: 'center', justifyContent: 'center' },
  dotInner: { width: 10, height: 10, borderRadius: 5 },
  chip: {
    minHeight: MIN_TOUCH,
    borderRadius: radius.chip,
    borderWidth: 1.5,
    paddingHorizontal: space.xl,
    alignItems: 'center',
    justifyContent: 'center',
  },
  day: {
    width: 68,
    minHeight: 92,
    borderRadius: radius.chip + 4,
    borderWidth: 1.5,
    alignItems: 'center',
    justifyContent: 'center',
    gap: 1,
  },
});
