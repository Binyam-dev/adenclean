import * as Haptics from 'expo-haptics';
import { Platform, Pressable, StyleSheet, View } from 'react-native';
import Svg, { Path } from 'react-native-svg';

import { usePalette } from './use-palette';

const STAR = 'M12 2.6l2.9 6 6.6.9-4.8 4.6 1.2 6.5L12 17.4l-5.9 3.2 1.2-6.5L2.5 9.5l6.6-.9z';

export function Stars({ value, onChange }: { value: number; onChange: (value: number) => void }) {
  const p = usePalette();
  return (
    <View accessibilityRole="radiogroup" accessibilityLabel="Rating" style={styles.row}>
      {[1, 2, 3, 4, 5].map((n) => {
        const on = n <= value;
        return (
          <Pressable
            key={n}
            accessibilityRole="radio"
            accessibilityState={{ checked: n === value }}
            accessibilityLabel={`${n} ${n === 1 ? 'star' : 'stars'}`}
            hitSlop={4}
            onPress={() => {
              if (Platform.OS !== 'web') void Haptics.selectionAsync();
              onChange(n);
            }}
            style={styles.hit}>
            <Svg width={34} height={34} viewBox="0 0 24 24">
              <Path
                d={STAR}
                fill={on ? p.accent : 'transparent'}
                stroke={on ? p.ink : p.inkSoft}
                strokeWidth={1.7}
                strokeLinejoin="round"
              />
            </Svg>
          </Pressable>
        );
      })}
    </View>
  );
}

const styles = StyleSheet.create({
  row: { flexDirection: 'row', gap: 2 },
  hit: { minWidth: 48, minHeight: 48, alignItems: 'center', justifyContent: 'center' },
});
