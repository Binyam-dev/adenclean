import { router, useFocusEffect } from 'expo-router';
import { useCallback, useState } from 'react';
import { Pressable, StyleSheet, View } from 'react-native';

import { Notice, StatusPill } from '@/components/Bits';
import { Button } from '@/components/Button';
import { Field } from '@/components/Field';
import { Screen } from '@/components/Screen';
import { Text } from '@/components/Text';
import { usePalette } from '@/components/use-palette';
import { ApiError, isGone, lookup, statusCache, type Lookup } from '@/lib/api';
import { statusCopy } from '@/lib/status';
import { listSaved, saveRequest, type SavedRequest } from '@/lib/storage';
import { radius, space } from '@/lib/theme';
import { extractToken, serviceTitle, speakDate, timeTitle } from '@/lib/validation';

type Row = { saved: SavedRequest; info: Lookup | null; failed: boolean };

export default function Requests() {
  const p = usePalette();
  const [rows, setRows] = useState<Row[] | null>(null);
  const [refreshing, setRefreshing] = useState(false);
  const [pasted, setPasted] = useState('');
  const [addError, setAddError] = useState<string | null>(null);
  const [adding, setAdding] = useState(false);

  // force: ask the server for every status (pull-to-refresh). Otherwise recent answers are
  // reused, so switching tabs or coming back from a request doesn't spend the lookup allowance.
  const load = useCallback(async (force = false) => {
    const saved = await listSaved();
    setRows(saved.map((item) => ({ saved: item, info: force ? null : statusCache.peek(item.token), failed: false })));
    // Fetch each status on its own so one slow or failed request doesn't hold up the rest.
    await Promise.all(
      saved.map(async (item) => {
        let next: Pick<Row, 'info' | 'failed'>;
        try {
          next = { info: await statusCache.get(item.token, force), failed: false };
        } catch {
          next = { info: null, failed: true };
        }
        setRows((current) =>
          current ? current.map((row) => (row.saved.reference === item.reference ? { ...row, ...next } : row)) : current,
        );
      }),
    );
  }, []);

  useFocusEffect(
    useCallback(() => {
      void load();
    }, [load]),
  );

  const onRefresh = async () => {
    setRefreshing(true);
    await load(true);
    setRefreshing(false);
  };

  const addByLink = async () => {
    const token = extractToken(pasted);
    if (!token) {
      setAddError("That doesn't look like an AdenClean link. Paste the whole link, or the 43-character code from it.");
      return;
    }
    setAddError(null);
    setAdding(true);
    try {
      const info = await lookup(token);
      statusCache.remember(token, info);
      await saveRequest({
        reference: `L${token.slice(0, 11).toUpperCase().replace(/[^A-Z0-9]/g, 'X')}`,
        token,
        createdAt: new Date().toISOString(),
        service: info.serviceType,
        date: info.preferredDate,
        time: '',
        imported: true,
      });
      setPasted('');
      await load();
    } catch (e) {
      setAddError(
        isGone(e)
          ? "AdenClean can't find a request for that link. Check that you copied all of it."
          : e instanceof ApiError
            ? e.message
            : "We couldn't add that request. Try again.",
      );
    } finally {
      setAdding(false);
    }
  };

  return (
    <Screen refreshing={refreshing} onRefresh={onRefresh}>
      <Text variant="title" accessibilityRole="header">
        Your requests
      </Text>

      {rows !== null && rows.length === 0 ? (
        <View style={[styles.empty, { backgroundColor: p.surface, borderColor: p.line }]}>
          <Text variant="heading">No requests yet</Text>
          <Text variant="body" tone="soft">
            When you send a request, it appears here so you can check its status and leave feedback after the service.
          </Text>
          <Button label="Request a cleaning" onPress={() => router.push('/new')} />
        </View>
      ) : null}

      <View style={styles.list}>
        {rows?.map(({ saved, info, failed }) => {
          const copy = info ? statusCopy(info.status) : null;
          return (
            <Pressable
              key={saved.reference}
              accessibilityRole="button"
              accessibilityLabel={`${serviceTitle(saved.service)}, ${speakDate(saved.date)}. ${
                copy ? copy.label : failed ? 'Status unavailable' : 'Checking status'
              }`}
              onPress={() => router.push({ pathname: '/request/[ref]', params: { ref: saved.reference } })}
              style={({ pressed }) => [styles.card, { backgroundColor: p.surface, borderColor: p.line, opacity: pressed ? 0.9 : 1 }]}>
              <Text variant="heading">{serviceTitle(saved.service)}</Text>
              <Text variant="small" tone="soft">
                {saved.time ? `${speakDate(saved.date)}, ${timeTitle(saved.time).toLowerCase()}` : speakDate(saved.date)}
              </Text>
              {copy ? (
                <StatusPill label={copy.label} tone={copy.tone} />
              ) : failed ? (
                <StatusPill label="Status unavailable" tone="wait" />
              ) : (
                <StatusPill label="Checking…" tone="wait" />
              )}
            </Pressable>
          );
        })}
      </View>

      {rows && rows.length > 0 ? (
        <Text variant="small" tone="soft">
          Pull down to refresh. Requests are saved on this phone only.
        </Text>
      ) : null}

      {rows !== null ? (
        <View style={[styles.add, { backgroundColor: p.surfaceDeep }]}>
          <Text variant="heading">Sent a request from the website?</Text>
          <Text variant="small" tone="soft">
            Paste the private link you were given and it appears here.
          </Text>
          <Field
            label="Private link or code"
            value={pasted}
            onChangeText={(v) => {
              setPasted(v);
              setAddError(null);
            }}
            autoCapitalize="none"
            error={addError}
            showError={!!addError}
            maxLength={600}
          />
          <Button label="Add request" variant="secondary" onPress={() => void addByLink()} loading={adding} disabled={pasted.trim() === ''} />
          {addError ? null : <Notice kind="info">Only paste links that AdenClean gave you.</Notice>}
        </View>
      ) : null}
    </Screen>
  );
}

const styles = StyleSheet.create({
  list: { gap: space.md },
  card: { borderRadius: radius.card, borderWidth: 1.5, padding: space.xl, gap: 8, minHeight: 48 },
  empty: { borderRadius: radius.hero - 6, borderWidth: 1.5, padding: space.xl, gap: space.lg },
  add: { borderRadius: radius.card, padding: space.xl, gap: space.md },
});
