import { useFocusEffect } from 'expo-router';
import { useCallback, useState } from 'react';
import { View } from 'react-native';

import { Notice } from '@/components/Bits';
import { Button } from '@/components/Button';
import { EmptyState, Header } from '@/components/Controls';
import { Screen } from '@/components/Screen';
import { Text } from '@/components/Text';
import { usePalette } from '@/components/use-palette';
import { ApiError } from '@/lib/api';
import { blockedLine } from '@/lib/moderation';
import { useSession } from '@/lib/session';
import { space } from '@/lib/theme';
import type { Block } from '@/lib/v1';

/** The people you have blocked, with a way to undo each block. */
export default function Blocked() {
  const p = usePalette();
  const { client, token, user } = useSession();
  const [blocks, setBlocks] = useState<Block[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    if (!token) return;
    try {
      setBlocks(await client.blocks());
      setError(null);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : 'Could not load your blocked list.');
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [token]);

  useFocusEffect(useCallback(() => void load(), [load]));

  const unblock = async (id: string) => {
    try {
      await client.unblock(id);
      await load();
    } catch (e) {
      setError(e instanceof ApiError ? e.message : 'Could not unblock. Try again.');
    }
  };

  return (
    <Screen>
      <Header title="Blocked people" />
      {!user ? <Text tone="soft">Sign in to see who you have blocked.</Text> : null}
      {error ? <Notice kind="error">{error}</Notice> : null}
      {user && blocks?.length === 0 ? (
        <EmptyState title="No one is blocked"
          body="If someone bothers you, open their offer or job and tap Block. They are not told." />
      ) : null}
      {blocks?.map((block) => (
        <View key={block.id} style={{ gap: space.sm, borderBottomWidth: 1, borderBottomColor: p.line, paddingBottom: space.md }}>
          <Text variant="bodyStrong">{blockedLine(block.name, block.created_at)}</Text>
          <Button variant="secondary" label="Unblock" onPress={() => void unblock(block.id)} />
        </View>
      ))}
      {blocks?.length ? (
        <Text variant="small" tone="soft">Unblocking lets you see each other&apos;s new jobs again. Offers that were withdrawn do not come back.</Text>
      ) : null}
    </Screen>
  );
}
