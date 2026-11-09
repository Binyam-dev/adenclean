import { useState } from 'react';
import { Modal, Pressable, ScrollView, StyleSheet, View } from 'react-native';

import { ApiError } from '@/lib/api';
import { canSubmitReport, REPORT_DETAIL_MAX, REPORT_REASONS, reportThanks } from '@/lib/moderation';
import { radius, space } from '@/lib/theme';

import { Notice } from './Bits';
import { Button } from './Button';
import { Chip } from './Choice';
import { Field } from './Field';
import { Text } from './Text';
import { usePalette } from './use-palette';

/** A sheet for reporting a job's notes or an offer. Nothing is sent until the person taps Send. */
export function ReportSheet({ visible, title, onClose, onSend }: {
  visible: boolean;
  title: string;
  onClose: () => void;
  onSend: (reason: string, detail: string) => Promise<{ merged: boolean }>;
}) {
  const p = usePalette();
  const [reason, setReason] = useState<string | null>(null);
  const [detail, setDetail] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [thanks, setThanks] = useState<string | null>(null);

  const close = () => {
    setReason(null);
    setDetail('');
    setError(null);
    setThanks(null);
    onClose();
  };

  const send = async () => {
    if (!reason) return;
    setBusy(true);
    setError(null);
    try {
      const result = await onSend(reason, detail);
      setThanks(reportThanks(result.merged));
    } catch (e) {
      setError(e instanceof ApiError ? e.message : 'The report did not go through. Try again.');
    } finally {
      setBusy(false);
    }
  };

  return (
    <Modal visible={visible} animationType="slide" transparent onRequestClose={close}>
      <View style={styles.backdrop}>
        <View style={[styles.sheet, { backgroundColor: p.bg, borderColor: p.line }]}>
          <ScrollView contentContainerStyle={{ gap: space.md }} keyboardShouldPersistTaps="handled">
            <Text variant="heading" accessibilityRole="header">{title}</Text>
            {thanks ? (
              <>
                <Notice kind="success">{thanks}</Notice>
                <Button label="Done" onPress={close} />
              </>
            ) : (
              <>
                <Text tone="soft">Why are you reporting this? The other person is not told it was you.</Text>
                <View style={styles.chips} accessibilityRole="radiogroup">
                  {REPORT_REASONS.map((r) => (
                    <Chip key={r.id} label={r.label} selected={reason === r.id} onPress={() => setReason(r.id)} />
                  ))}
                </View>
                <Field label="Anything else we should know?" optional multiline maxLength={REPORT_DETAIL_MAX}
                  value={detail} onChangeText={setDetail} counter={`${detail.length} / ${REPORT_DETAIL_MAX}`} />
                {error ? <Notice kind="error">{error}</Notice> : null}
                <Button label="Send report" onPress={() => void send()} loading={busy}
                  disabled={!canSubmitReport(reason, detail)} testID="report-send" />
                <Pressable accessibilityRole="button" onPress={close} style={styles.cancel}>
                  <Text tone="soft">Cancel</Text>
                </Pressable>
              </>
            )}
          </ScrollView>
        </View>
      </View>
    </Modal>
  );
}

const styles = StyleSheet.create({
  backdrop: { flex: 1, justifyContent: 'flex-end', backgroundColor: 'rgba(0,0,0,0.4)' },
  sheet: { maxHeight: '88%', borderTopLeftRadius: radius.card, borderTopRightRadius: radius.card, borderWidth: 1.5, padding: space.xl },
  chips: { flexDirection: 'row', flexWrap: 'wrap', gap: space.sm },
  cancel: { alignItems: 'center', minHeight: 44, justifyContent: 'center' },
});
