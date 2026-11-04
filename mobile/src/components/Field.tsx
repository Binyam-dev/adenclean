import { useState } from 'react';
import { StyleSheet, TextInput, View, type TextInputProps } from 'react-native';

import { fonts, radius, space, type as typeScale } from '@/lib/theme';

import { Text } from './Text';
import { usePalette } from './use-palette';

type Props = Pick<
  TextInputProps,
  'value' | 'onChangeText' | 'keyboardType' | 'autoCapitalize' | 'autoComplete' | 'textContentType' | 'returnKeyType' | 'onSubmitEditing' | 'maxLength' | 'placeholder'
> & {
  label: string;
  hint?: string;
  error?: string | null;
  multiline?: boolean;
  optional?: boolean;
  /** Shows a short note such as "123 / 800" under a long text box. */
  counter?: string;
  /** Show the error even before the person has left the field. */
  showError?: boolean;
  testID?: string;
};

export function Field({ label, hint, error, multiline, optional, counter, testID, value, showError: forced, ...input }: Props) {
  const p = usePalette();
  const [focused, setFocused] = useState(false);
  const [touched, setTouched] = useState(false);
  const showError = (touched || !!forced) && !!error;

  return (
    <View style={styles.wrap}>
      <Text variant="bodyStrong" style={styles.label}>
        {label}
        {optional ? (
          <Text variant="small" tone="soft">
            {'  optional'}
          </Text>
        ) : null}
      </Text>
      <TextInput
        {...input}
        testID={testID}
        value={value}
        multiline={multiline}
        accessibilityLabel={label}
        accessibilityHint={hint}
        placeholderTextColor={p.inkSoft}
        onFocus={() => setFocused(true)}
        onBlur={() => {
          setFocused(false);
          setTouched(true);
        }}
        style={[
          typeScale.body,
          {
            color: p.ink,
            backgroundColor: p.surface,
            borderColor: showError ? p.error : focused ? p.focus : p.line,
            borderWidth: focused || showError ? 2 : 1.5,
            fontFamily: fonts.body,
          },
          styles.input,
          multiline && styles.multiline,
        ]}
      />
      {showError ? (
        <Text variant="small" tone="error" style={styles.below} accessibilityLiveRegion="polite">
          {error}
        </Text>
      ) : hint ? (
        <Text variant="small" tone="soft" style={styles.below}>
          {hint}
        </Text>
      ) : null}
      {counter !== undefined ? (
        <Text variant="caption" tone="soft" style={[styles.below, { textAlign: 'right' }]}>
          {counter}
        </Text>
      ) : null}
    </View>
  );
}

const styles = StyleSheet.create({
  wrap: { gap: 6 },
  label: { marginBottom: 2 },
  input: {
    minHeight: 52,
    borderRadius: radius.control,
    paddingHorizontal: space.lg,
    paddingVertical: 12,
  },
  multiline: { minHeight: 112, textAlignVertical: 'top', paddingTop: 14 },
  below: { marginTop: 2 },
});
