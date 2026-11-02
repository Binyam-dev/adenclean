import type { ReactNode } from 'react';
import { RefreshControl, ScrollView, StyleSheet, View } from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';

import { MAX_WIDTH, space } from '@/lib/theme';

import { usePalette } from './use-palette';

type Props = {
  children: ReactNode;
  /** Extra room at the bottom, for a fixed action bar or the tab bar. */
  bottomInset?: number;
  refreshing?: boolean;
  onRefresh?: () => void;
};

export function Screen({ children, bottomInset = 0, refreshing, onRefresh }: Props) {
  const p = usePalette();
  const insets = useSafeAreaInsets();
  return (
    <ScrollView
      style={{ backgroundColor: p.bg }}
      contentContainerStyle={{
        paddingTop: insets.top + space.lg,
        paddingBottom: insets.bottom + space.huge + bottomInset,
        alignItems: 'center',
      }}
      keyboardShouldPersistTaps="handled"
      keyboardDismissMode="on-drag"
      showsVerticalScrollIndicator={false}
      refreshControl={
        onRefresh ? <RefreshControl refreshing={!!refreshing} onRefresh={onRefresh} tintColor={p.primary} /> : undefined
      }>
      <View style={styles.column}>{children}</View>
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  column: { width: '100%', maxWidth: MAX_WIDTH, paddingHorizontal: space.xl, gap: space.xl },
});
