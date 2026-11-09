import { useSyncExternalStore, type ReactNode } from 'react';
import { RefreshControl, ScrollView, StyleSheet, View } from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';

import { isSlow, subscribeSlow } from '@/lib/net';
import { MAX_WIDTH, space } from '@/lib/theme';

import { Notice } from './Bits';
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
  // True once a request has been waiting a few seconds: the server may be waking from sleep.
  const slow = useSyncExternalStore(subscribeSlow, isSlow, isSlow);
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
      <View style={styles.column}>
        {slow ? (
          <Notice kind="info" title="Waking AdenClean up">
            The first request of the day can take up to a minute. Please keep this screen open.
          </Notice>
        ) : null}
        {children}
      </View>
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  column: { width: '100%', maxWidth: MAX_WIDTH, paddingHorizontal: space.xl, gap: space.xl },
});
