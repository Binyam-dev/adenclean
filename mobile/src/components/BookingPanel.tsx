import { useFocusEffect } from 'expo-router';
import { useCallback, useState } from 'react';
import { View } from 'react-native';

import { ApiError } from '@/lib/api';
import { confirmAction } from '@/lib/confirm';
import { formatCents } from '@/lib/market';
import { payWithSheet } from '@/lib/pay';
import { bookingActions, bookingSummary, tipOptions, type BookingAction } from '@/lib/steps';
import { space } from '@/lib/theme';
import type { Booking, Client } from '@/lib/v1';

import { Notice } from './Bits';
import { Button } from './Button';
import { Chip } from './Choice';
import { Text } from './Text';

/** Pay, check in and out, confirm, tip and cancel, for a booked job. Hidden when payments are off. */
export function BookingPanel({ client, jobId, role, jobStatus, onChanged }: {
  client: Client; jobId: string; role: 'customer' | 'cleaner'; jobStatus: string; onChanged: () => Promise<void> | void;
}) {
  const [booking, setBooking] = useState<Booking | null>(null);
  const [busy, setBusy] = useState<BookingAction | null>(null);
  const [message, setMessage] = useState<{ kind: 'error' | 'success'; text: string } | null>(null);
  const [tip, setTip] = useState<number | null>(null);

  const load = useCallback(async () => {
    try {
      setBooking(await client.booking(jobId));
    } catch {
      setBooking(null); // no booking yet, or payments are off
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [jobId, jobStatus]);

  useFocusEffect(useCallback(() => void load(), [load]));

  if (!booking) return null;

  const run = async (action: BookingAction, fn: () => Promise<string | void>) => {
    setBusy(action);
    setMessage(null);
    try {
      const done = await fn();
      if (done) setMessage({ kind: 'success', text: done });
      await load();
      await onChanged();
    } catch (e) {
      setMessage({ kind: 'error', text: e instanceof ApiError ? e.message : 'That did not go through. Try again.' });
    } finally {
      setBusy(null);
    }
  };

  // The card is entered in Stripe's own sheet. The server marks the booking paid when Stripe confirms.
  const charge = async (start: () => Promise<{ clientSecret: string; publishableKey: string }>, thanks: string) => {
    const { clientSecret, publishableKey } = await start();
    const result = await payWithSheet(clientSecret, publishableKey);
    if (result.status === 'paid') return thanks;
    if (result.status === 'canceled') return;
    throw new ApiError('client', 0, result.message ?? 'The payment did not go through.');
  };

  const cancel = async () => {
    const late = role === 'customer' && booking.payment_status === 'paid';
    const yes = await confirmAction({
      title: 'Cancel this booking?',
      message: late
        ? 'You get a full refund if the job is more than 24 hours away. Closer than that, the cleaner keeps 25% for the lost day.'
        : 'The booking ends and the job closes.',
      confirmLabel: 'Cancel booking', cancelLabel: 'Keep booking', destructive: true,
    });
    if (!yes) return;
    await run('cancel', async () => {
      const r = await client.cancelBooking(jobId);
      return r.refundCents ? `Cancelled. ${formatCents(r.refundCents)} goes back to your card.` : 'Cancelled.';
    });
  };

  const actions = bookingActions(booking, role, jobStatus);
  const price = booking.price_cents;
  const has = (a: BookingAction) => actions.includes(a);

  return (
    <View style={{ gap: space.md }}>
      <Text variant="heading">{role === 'customer' ? 'Payment' : 'Your pay'}</Text>
      <Text tone="soft">{bookingSummary(booking, role, jobStatus)}</Text>
      {role === 'customer' && booking.total_cents ? <Text variant="bodyStrong">{`Total ${formatCents(booking.total_cents)}`}</Text> : null}
      {role === 'cleaner' && booking.payout_cents != null ? (
        <Text variant="bodyStrong">{`You receive ${formatCents(booking.payout_cents)} after the ${formatCents(booking.fee_cents)} fee, plus any tip.`}</Text>
      ) : null}
      {message ? <Notice kind={message.kind}>{message.text}</Notice> : null}

      {has('pay') ? (
        <Button label={`Pay ${formatCents(price)}`} loading={busy === 'pay'} testID="booking-pay"
          onPress={() => void run('pay', () => charge(() => client.startPayment(jobId), 'Paid. Your cleaner can start on the day.'))} />
      ) : null}
      {has('check_in') ? (
        <Button label="I have arrived: check in" loading={busy === 'check_in'} onPress={() => void run('check_in', () => client.bookingStep(jobId, 'check-in'))} />
      ) : null}
      {has('check_out') ? (
        <Button label="Job done: check out" loading={busy === 'check_out'} onPress={() => void run('check_out', () => client.bookingStep(jobId, 'check-out'))} />
      ) : null}
      {has('confirm') ? (
        <Button label="Confirm the cleaning is done" loading={busy === 'confirm'}
          onPress={() => void run('confirm', async () => { await client.bookingStep(jobId, 'confirm'); return 'Confirmed. Your cleaner is paid.'; })} />
      ) : null}
      {has('tip') ? (
        <View style={{ gap: space.sm }}>
          <Text variant="bodyStrong">Add a tip (100% goes to your cleaner)</Text>
          <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: space.sm }}>
            {tipOptions(price).map((cents) => (
              <Chip key={cents} label={formatCents(cents)} selected={tip === cents} onPress={() => setTip(cents)} />
            ))}
          </View>
          <Button variant="secondary" label={tip ? `Tip ${formatCents(tip)}` : 'Choose a tip'} disabled={!tip} loading={busy === 'tip'}
            onPress={() => void run('tip', () => charge(() => client.startTip(jobId, tip!), 'Thank you. Your tip is on its way.'))} />
        </View>
      ) : null}
      {has('cancel') ? <Button variant="quiet" label="Cancel this booking" loading={busy === 'cancel'} onPress={() => void cancel()} /> : null}
    </View>
  );
}
