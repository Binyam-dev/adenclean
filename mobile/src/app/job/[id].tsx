import { useFocusEffect, useLocalSearchParams } from 'expo-router';
import { useCallback, useState } from 'react';
import { StyleSheet, View } from 'react-native';

import { Notice, StatusPill } from '@/components/Bits';
import { Header, NextSteps } from '@/components/Controls';
import { Button } from '@/components/Button';
import { Field } from '@/components/Field';
import { JobCard } from '@/components/JobCard';
import { Screen } from '@/components/Screen';
import { Text } from '@/components/Text';
import { usePalette } from '@/components/use-palette';
import { ApiError } from '@/lib/api';
import { confirmAction } from '@/lib/confirm';
import { checkPrice, formatCents, myTurn, offerStatusLabel, parseDollars, payoutAfterFee, PLATFORM_FEE_BPS } from '@/lib/market';
import { useSession } from '@/lib/session';
import { radius, space } from '@/lib/theme';
import type { Job, Offer } from '@/lib/v1';

function OfferCard({ offer, me, onAction }: { offer: Offer; me: 'customer' | 'cleaner';
  onAction: (action: 'accept' | 'decline' | 'withdraw' | 'counter', price?: number) => Promise<void> }) {
  const p = usePalette();
  const [price, setPrice] = useState('');
  const [busy, setBusy] = useState(false);
  const turn = myTurn(offer, me);
  const open = offer.status === 'pending' || offer.status === 'countered';
  const canCounter = turn && offer.counter_rounds < 2;
  const run = async (action: 'accept' | 'decline' | 'withdraw' | 'counter', value?: number) => {
    setBusy(true);
    try {
      await onAction(action, value);
    } finally {
      setBusy(false);
    }
  };
  const priceError = price ? checkPrice(price) : null;
  return (
    <View style={[styles.card, { backgroundColor: p.surface, borderColor: p.line }]}>
      <View style={styles.row}>
        <Text variant="heading">{formatCents(offer.price_cents)}</Text>
        <StatusPill label={offerStatusLabel(offer.status)} tone={offer.status === 'accepted' ? 'good' : open ? 'wait' : 'stop'} />
      </View>
      {offer.cleaner_name ? <Text variant="bodyStrong">{offer.cleaner_name}</Text> : null}
      {offer.message ? <Text tone="soft">{offer.message}</Text> : null}
      {open && !turn ? <Text tone="soft">Waiting for the other person to answer.</Text> : null}
      {turn ? (
        <>
          <Button label={`Accept ${formatCents(offer.price_cents)}`} onPress={() => void run('accept')} loading={busy} />
          {canCounter ? (
            <>
              <Field label="Or suggest a price" value={price} onChangeText={setPrice} keyboardType="decimal-pad"
                error={priceError} showError={!!price} hint={2 - offer.counter_rounds === 1 ? 'Last counter-offer' : `${2 - offer.counter_rounds} counter-offers left`} />
              <Button variant="secondary" label="Send counter-offer" disabled={!price || !!priceError}
                onPress={() => void run('counter', parseDollars(price)!)} />
            </>
          ) : null}
          <Button variant="quiet" label="Decline" onPress={() => void run('decline')} />
        </>
      ) : null}
      {me === 'cleaner' && open ? <Button variant="quiet" label="Withdraw my offer" onPress={() => void run('withdraw')} /> : null}
    </View>
  );
}

export default function JobDetail() {
  const { id } = useLocalSearchParams<{ id: string }>();
  const { client, token } = useSession();
  const [job, setJob] = useState<Job | null>(null);
  const [role, setRole] = useState<'customer' | 'cleaner'>('customer');
  const [offers, setOffers] = useState<Offer[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [newPrice, setNewPrice] = useState('');
  const [message, setMessage] = useState('');
  const [sending, setSending] = useState(false);

  const load = useCallback(async () => {
    try {
      const view = await client.job(String(id));
      setJob(view.job);
      setRole(view.role);
      setOffers(view.role === 'customer' ? await client.offers(String(id)) : view.myOffer ? [view.myOffer] : []);
      setError(null);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : 'Could not load this job.');
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [id, token]);

  useFocusEffect(useCallback(() => void load(), [load]));

  const act = async (offerId: string, action: 'accept' | 'decline' | 'withdraw' | 'counter', price?: number) => {
    if (action === 'accept') {
      const yes = await confirmAction({ title: 'Book this price?', message: 'Accepting locks the price and books the job. Other offers close.',
        confirmLabel: 'Book it', cancelLabel: 'Not yet' });
      if (!yes) return;
    }
    try {
      if (action === 'counter') await client.counter(offerId, price!);
      else await client.answer(offerId, action);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : 'That did not go through. Try again.');
    }
    await load();
  };

  const sendOffer = async () => {
    const problem = checkPrice(newPrice);
    if (problem) return setError(problem);
    setSending(true);
    try {
      await client.sendOffer(String(id), parseDollars(newPrice)!, message);
      setNewPrice('');
      setMessage('');
      await load();
    } catch (e) {
      setError(e instanceof ApiError ? e.message : 'Could not send the offer.');
    } finally {
      setSending(false);
    }
  };

  const cancel = async () => {
    const yes = await confirmAction({ title: 'Cancel this job?', message: 'Cleaners can no longer send offers.',
      confirmLabel: 'Cancel job', cancelLabel: 'Keep job', destructive: true });
    if (!yes) return;
    try {
      await client.cancelJob(String(id));
      await load();
    } catch (e) {
      setError(e instanceof ApiError ? e.message : 'Could not cancel the job.');
    }
  };

  return (
    <Screen>
      <Header title={role === 'customer' ? 'Your job' : 'Job details'} />
      {error ? <Notice kind="error">{error}</Notice> : null}
      {job ? (
        <JobCard
          // A cleaner's view has no booked price; show the accepted offer's price instead.
          job={job.price_cents == null && offers[0]?.status === 'accepted' ? { ...job, price_cents: offers[0].price_cents } : job}
          showStatus
        />
      ) : !error ? <Text tone="soft">Loading…</Text> : null}
      {job?.notes ? (
        <View style={{ gap: space.xs }}>
          <Text variant="bodyStrong">Notes from the customer</Text>
          <Text tone="soft">{job.notes}</Text>
        </View>
      ) : null}

      {job?.status === 'booked' ? (
        <NextSteps
          title="What happens next"
          steps={role === 'customer'
            ? [`The price is locked at ${formatCents(job.price_cents ?? offers.find((o) => o.status === 'accepted')?.price_cents ?? 0)}.`,
               'AdenClean emails you and your cleaner to confirm the address and arrival time.',
               'After the cleaning, you will be able to leave a review.']
            : ['The price is locked. Keep the date free.',
               'AdenClean emails you and the customer to confirm the address and arrival time.',
               'Bring your supplies if the job says you will.']}
        />
      ) : null}

      {job && role === 'cleaner' && offers.length === 0 && job.status === 'open' ? (
        <View style={{ gap: space.md }}>
          <Text variant="heading">Send an offer</Text>
          <Text tone="soft">Name your price for this job. You keep the price minus the AdenClean {PLATFORM_FEE_BPS / 100}% fee, and all tips.</Text>
          <Field label="Your price" value={newPrice} onChangeText={setNewPrice} keyboardType="decimal-pad"
            hint={parseDollars(newPrice) ? `You receive ${formatCents(payoutAfterFee(parseDollars(newPrice)!).payout)} after the ${formatCents(payoutAfterFee(parseDollars(newPrice)!).fee)} fee.` : undefined} />
          <Field label="Message" optional multiline maxLength={500} value={message} onChangeText={setMessage}
            hint="When you can come and what you will bring. Don't include phone numbers or emails." />
          <Button label="Send offer" onPress={() => void sendOffer()} loading={sending} testID="offer-send" />
        </View>
      ) : null}

      {offers.length ? <Text variant="heading">{role === 'customer' ? `Offers (${offers.length})` : 'Your offer'}</Text> : null}
      {role === 'customer' && job?.status === 'open' && offers.length === 0 ? (
        <Text tone="soft">No offers yet. Cleaners near you can see this job now.</Text>
      ) : null}
      {offers.map((offer) => (
        <OfferCard key={offer.id} offer={offer} me={role} onAction={(action, price) => act(offer.id, action, price)} />
      ))}

      {role === 'customer' && job && ['open', 'expired'].includes(job.status) ? (
        <Button variant="quiet" label="Cancel this job" onPress={() => void cancel()} />
      ) : null}
    </Screen>
  );
}

const styles = StyleSheet.create({
  card: { borderRadius: radius.card, borderWidth: 1.5, padding: space.xl, gap: space.md },
  row: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center' },
});
