import * as Haptics from 'expo-haptics';
import { ActivityIndicator, Platform, Pressable, StyleSheet, View } from 'react-native';

import { MIN_TOUCH, radius } from '@/lib/theme';

import { Text } from './Text';
import { usePalette } from './use-palette';

type Props = {
  label: string;
  onPress: () => void;
  variant?: 'primary' | 'secondary' | 'quiet' | 'onHero';
  loading?: boolean;
  disabled?: boolean;
  /** Spoken label when it should say more than the visible text. */
  accessibilityLabel?: string;
  testID?: string;
};

export function Button({ label, onPress, variant = 'primary', loading, disabled, accessibilityLabel, testID }: Props) {
  const p = usePalette();
  const inactive = disabled || loading;

  const look = {
    primary: { bg: p.primary, fg: p.onPrimary, border: 'transparent' },
    secondary: { bg: 'transparent', fg: p.ink, border: p.line },
    quiet: { bg: 'transparent', fg: p.primary, border: 'transparent' },
    onHero: { bg: p.accent, fg: p.onAccent, border: 'transparent' },
  }[variant];

  const handlePress = () => {
    if (inactive) return;
    if (Platform.OS !== 'web') void Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Light);
    onPress();
  };

  return (
    <Pressable
      testID={testID}
      onPress={handlePress}
      accessibilityRole="button"
      accessibilityLabel={accessibilityLabel ?? label}
      accessibilityState={{ disabled: !!inactive, busy: !!loading }}
      style={({ pressed }) => [
        styles.base,
        {
          backgroundColor: look.bg,
          borderColor: look.border,
          borderWidth: variant === 'secondary' ? 1.5 : 0,
          opacity: inactive ? 0.45 : pressed ? 0.85 : 1,
          transform: [{ scale: pressed && !inactive ? 0.985 : 1 }],
        },
      ]}>
      {loading ? (
        <ActivityIndicator color={look.fg} />
      ) : (
        <View>
          <Text variant="bodyStrong" style={{ color: look.fg, textAlign: 'center' }}>
            {label}
          </Text>
        </View>
      )}
    </Pressable>
  );
}

const styles = StyleSheet.create({
  base: {
    minHeight: MIN_TOUCH + 4,
    borderRadius: radius.control,
    paddingHorizontal: 22,
    paddingVertical: 12,
    alignItems: 'center',
    justifyContent: 'center',
  },
});
