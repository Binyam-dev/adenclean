import { StyleSheet, View } from 'react-native';
import Svg, { Path } from 'react-native-svg';

import { radius, space } from '@/lib/theme';
import type { Tone } from '@/lib/status';

import { Text } from './Text';
import { usePalette } from './use-palette';

/** The small house mark plus the wordmark. */
export function Wordmark({ onHero = false }: { onHero?: boolean }) {
  const p = usePalette();
  const color = onHero ? p.onHero : p.ink;
  return (
    <View style={styles.wordmark} accessible accessibilityRole="header" accessibilityLabel="AdenClean">
      <View style={[styles.mark, { backgroundColor: p.primary }]}>
        <Svg width={22} height={22} viewBox="0 0 40 40" fill="none">
          <Path
            d="M8 28.5V18.2L20 8l12 10.2v10.3a3.5 3.5 0 0 1-3.5 3.5h-17A3.5 3.5 0 0 1 8 28.5Z"
            stroke={p.onPrimary}
            strokeWidth={2.6}
            strokeLinejoin="round"
          />
          <Path d="M15.5 31.5v-9h9v9" stroke={p.onPrimary} strokeWidth={2.6} strokeLinecap="round" strokeLinejoin="round" />
          <Path d="M27.2 8.6l4.7-3.9M20 3.5v-2" stroke={p.accent} strokeWidth={2.6} strokeLinecap="round" />
        </Svg>
      </View>
      <Text variant="heading" style={{ color, fontSize: 22, letterSpacing: -0.6 }}>
        aden<Text variant="heading" style={{ color: onHero ? p.accent : p.inkSoft, fontSize: 22, letterSpacing: -0.6 }}>clean</Text>
      </Text>
    </View>
  );
}

/** An inline message: a problem to fix, a success, or a plain note. */
export function Notice({ kind = 'info', title, children }: { kind?: 'info' | 'error' | 'success'; title?: string; children?: string }) {
  const p = usePalette();
  const bg = kind === 'error' ? p.errorBg : kind === 'success' ? p.successBg : p.surfaceDeep;
  const fg = kind === 'error' ? p.error : kind === 'success' ? p.success : p.ink;
  return (
    <View
      accessible
      accessibilityLiveRegion="polite"
      accessibilityRole={kind === 'error' ? 'alert' : undefined}
      style={[styles.notice, { backgroundColor: bg }]}>
      {title ? (
        <Text variant="bodyStrong" style={{ color: fg }}>
          {title}
        </Text>
      ) : null}
      {children ? (
        <Text variant="small" style={{ color: fg }}>
          {children}
        </Text>
      ) : null}
    </View>
  );
}

/** A status label. Colour is never the only signal: the words say it too. */
export function StatusPill({ label, tone }: { label: string; tone: Tone }) {
  const p = usePalette();
  const bg = tone === 'good' ? p.accent : tone === 'done' ? p.primary : tone === 'stop' ? p.errorBg : p.surfaceDeep;
  const fg = tone === 'good' ? p.onAccent : tone === 'done' ? p.onPrimary : tone === 'stop' ? p.error : p.ink;
  return (
    <View style={[styles.pill, { backgroundColor: bg }]}>
      <Text variant="caption" style={{ color: fg }}>
        {label}
      </Text>
    </View>
  );
}

export function Rule() {
  const p = usePalette();
  return <View style={{ height: StyleSheet.hairlineWidth * 2, backgroundColor: p.line }} />;
}

const styles = StyleSheet.create({
  wordmark: { flexDirection: 'row', alignItems: 'center', gap: space.sm + 2 },
  mark: { width: 36, height: 36, borderRadius: 11, alignItems: 'center', justifyContent: 'center' },
  notice: { borderRadius: radius.control, padding: space.lg, gap: 4 },
  pill: { alignSelf: 'flex-start', borderRadius: radius.pill, paddingHorizontal: 12, paddingVertical: 5 },
});
