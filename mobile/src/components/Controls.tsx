import * as Haptics from 'expo-haptics';
import { router } from 'expo-router';
import type { ReactNode } from 'react';
import { Platform, Pressable, StyleSheet, View } from 'react-native';
import Svg, { Path } from 'react-native-svg';

import { MIN_TOUCH, radius, space } from '@/lib/theme';

import { House } from './House';
import { Text } from './Text';
import { usePalette } from './use-palette';

function tap() {
  if (Platform.OS !== 'web') void Haptics.selectionAsync();
}

/** Screen header: a back control and the screen's title, announced as a heading. */
export function Header({ title, onBack }: { title: string; onBack?: () => void }) {
  const p = usePalette();
  const back = onBack ?? (() => (router.canGoBack() ? router.back() : router.replace('/market')));
  return (
    <View style={styles.header}>
      <Pressable accessibilityRole="button" accessibilityLabel="Back" onPress={back} hitSlop={8}
        style={({ pressed }) => [styles.back, { backgroundColor: p.surface, borderColor: p.line, opacity: pressed ? 0.7 : 1 }]}>
        <Svg width={20} height={20} viewBox="0 0 24 24" fill="none" stroke={p.ink} strokeWidth={2.2} strokeLinecap="round" strokeLinejoin="round">
          <Path d="M15 5l-7 7 7 7" />
        </Svg>
      </Pressable>
      <Text variant="title" accessibilityRole="header" style={{ flex: 1 }} numberOfLines={2}>
        {title}
      </Text>
    </View>
  );
}

/** Two or three mutually exclusive modes, like Hire / Work. */
export function Segmented<T extends string>({ options, value, onChange, label }: {
  options: { id: T; title: string }[]; value: T; onChange: (id: T) => void; label: string;
}) {
  const p = usePalette();
  return (
    <View accessibilityRole="tablist" accessibilityLabel={label} style={[styles.segmented, { backgroundColor: p.surfaceDeep }]}>
      {options.map((o) => {
        const on = o.id === value;
        return (
          <Pressable key={o.id} accessibilityRole="tab" accessibilityState={{ selected: on }} accessibilityLabel={o.title}
            onPress={() => { tap(); onChange(o.id); }}
            style={[styles.segment, on && { backgroundColor: p.surface, shadowColor: '#000', shadowOpacity: 0.08, shadowRadius: 6, shadowOffset: { width: 0, height: 2 } }]}>
            <Text variant="bodyStrong" style={{ color: on ? p.ink : p.inkSoft }}>{o.title}</Text>
          </Pressable>
        );
      })}
    </View>
  );
}

function StepButton({ sign, label, disabled, onPress }: { sign: '−' | '+'; label: string; disabled: boolean; onPress: () => void }) {
  const p = usePalette();
  return (
    <Pressable accessibilityRole="button" accessibilityLabel={`${sign === '+' ? 'More' : 'Fewer'} ${label.toLowerCase()}`}
      accessibilityState={{ disabled }} disabled={disabled} onPress={() => { tap(); onPress(); }}
      style={({ pressed }) => [styles.stepBtn, { borderColor: p.line, backgroundColor: p.surface, opacity: disabled ? 0.35 : pressed ? 0.7 : 1 }]}>
      <Text variant="heading">{sign}</Text>
    </Pressable>
  );
}

/** A − n + control for small counts (rooms). */
export function Stepper({ label, value, onChange, min, max }: {
  label: string; value: number; onChange: (n: number) => void; min: number; max: number;
}) {
  return (
    <View style={styles.stepper}>
      <Text variant="bodyStrong" style={{ flex: 1 }}>{label}</Text>
      <StepButton sign="−" label={label} disabled={value <= min} onPress={() => onChange(value - 1)} />
      <Text variant="heading" accessibilityLiveRegion="polite" accessibilityLabel={`${label}: ${value}`} style={styles.stepValue}>
        {value}
      </Text>
      <StepButton sign="+" label={label} disabled={value >= max} onPress={() => onChange(value + 1)} />
    </View>
  );
}

/** A real checkbox: box plus sentence, with optional inline links after it. */
export function Checkbox({ checked, onChange, children }: { checked: boolean; onChange: (v: boolean) => void; children: ReactNode }) {
  const p = usePalette();
  return (
    <Pressable accessibilityRole="checkbox" accessibilityState={{ checked }} onPress={() => { tap(); onChange(!checked); }}
      style={styles.checkRow}>
      <View style={[styles.box, { borderColor: checked ? p.primary : p.inkSoft, backgroundColor: checked ? p.primary : 'transparent' }]}>
        {checked ? (
          <Svg width={16} height={16} viewBox="0 0 24 24" fill="none" stroke={p.onPrimary} strokeWidth={3} strokeLinecap="round" strokeLinejoin="round">
            <Path d="M5 12.5l4.5 4.5L19 7" />
          </Svg>
        ) : null}
      </View>
      <View style={{ flex: 1 }}>{children}</View>
    </Pressable>
  );
}

/** An empty list: the house mark, a sentence about what belongs here, and the next step. */
export function EmptyState({ title, body, action }: { title: string; body: string; action?: ReactNode }) {
  const p = usePalette();
  return (
    <View style={[styles.empty, { backgroundColor: p.surface, borderColor: p.line }]}>
      <House lit={[true, false, false, false]} size={96} />
      <Text variant="heading" style={{ textAlign: 'center' }}>{title}</Text>
      <Text tone="soft" style={{ textAlign: 'center' }}>{body}</Text>
      {action}
    </View>
  );
}

/** Numbered "what happens next" steps after a booking. */
export function NextSteps({ title, steps }: { title: string; steps: string[] }) {
  const p = usePalette();
  return (
    <View style={[styles.next, { backgroundColor: p.surfaceDeep }]} accessible accessibilityLabel={`${title}. ${steps.join('. ')}`}>
      <Text variant="heading">{title}</Text>
      {steps.map((s, i) => (
        <View key={s} style={styles.nextRow}>
          <View style={[styles.num, { backgroundColor: p.accent }]}>
            <Text variant="caption" tone="onAccent">{i + 1}</Text>
          </View>
          <Text style={{ flex: 1 }}>{s}</Text>
        </View>
      ))}
    </View>
  );
}

const styles = StyleSheet.create({
  header: { flexDirection: 'row', alignItems: 'center', gap: space.md },
  back: { width: MIN_TOUCH, height: MIN_TOUCH, borderRadius: radius.pill, borderWidth: 1.5, alignItems: 'center', justifyContent: 'center' },
  segmented: { flexDirection: 'row', borderRadius: radius.control, padding: 4, gap: 4 },
  segment: { flex: 1, minHeight: MIN_TOUCH - 4, borderRadius: radius.control - 4, alignItems: 'center', justifyContent: 'center' },
  stepper: { flexDirection: 'row', alignItems: 'center', gap: space.md, minHeight: MIN_TOUCH },
  stepBtn: { width: MIN_TOUCH, height: MIN_TOUCH, borderRadius: radius.pill, borderWidth: 1.5, alignItems: 'center', justifyContent: 'center' },
  stepValue: { minWidth: 28, textAlign: 'center' },
  checkRow: { flexDirection: 'row', gap: space.md, alignItems: 'flex-start', minHeight: MIN_TOUCH, paddingVertical: 4 },
  box: { width: 26, height: 26, borderRadius: 8, borderWidth: 2, alignItems: 'center', justifyContent: 'center', marginTop: 1 },
  empty: { borderRadius: radius.card, borderWidth: 1.5, padding: space.xl, gap: space.md, alignItems: 'center' },
  next: { borderRadius: radius.card, padding: space.xl, gap: space.md },
  nextRow: { flexDirection: 'row', gap: space.md, alignItems: 'flex-start' },
  num: { width: 24, height: 24, borderRadius: 12, alignItems: 'center', justifyContent: 'center', marginTop: 1 },
});
