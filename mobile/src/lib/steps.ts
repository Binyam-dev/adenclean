// Pure rules for the cleaner application checklist and the booking actions. The server
// enforces every rule; these only decide what the screens show. No network here.

import type { Booking, Vetting } from './v1';

export type StepState = 'done' | 'now' | 'waiting' | 'later' | 'problem';

export type Step = { id: 'apply' | 'authorize' | 'identity' | 'background' | 'review'; title: string; detail: string; state: StepState };

/** The five steps of becoming a cleaner, with where this application stands on each. */
export function vettingSteps(v: Vetting | null): Step[] {
  const signed = !!v?.consent_at;
  const identity: Step = { id: 'identity', title: 'Verify your identity', state: 'later',
    detail: 'A photo of your government ID and a selfie, through Stripe.' };
  if (v?.identity_status === 'verified') Object.assign(identity, { state: 'done', detail: 'Verified.' });
  else if (v?.identity_status === 'pending') Object.assign(identity, { state: 'waiting', detail: 'Waiting for Stripe. This usually takes a few minutes.' });
  else if (v?.identity_status === 'failed') Object.assign(identity, { state: 'problem', detail: 'Stripe could not verify your ID. Try again with a clear photo in good light.' });
  else if (signed) identity.state = 'now';

  const background: Step = { id: 'background', title: 'Background check', state: 'later',
    detail: 'Through Checkr. You enter your Social Security number on their form, never in this app.' };
  if (['clear', 'consider', 'suspended'].includes(v?.background_status ?? '')) Object.assign(background, { state: 'done', detail: 'Checkr finished your report.' });
  else if (v?.background_status === 'invited') Object.assign(background, { state: 'waiting', detail: 'Finish the Checkr form if you have not. Checkr usually takes 1 to 3 business days.' });
  else if (signed) background.state = 'now';

  const review: Step = { id: 'review', title: 'AdenClean review', state: 'later', detail: 'A person at AdenClean reviews your checks.' };
  if (v?.status === 'approved') Object.assign(review, { state: 'done', detail: 'Approved.' });
  else if (v?.status === 'in_review') Object.assign(review, { state: 'waiting', detail: 'We are reviewing your checks. We email you when we decide.' });
  else if (v?.status === 'pre_adverse' || v?.status === 'denied') Object.assign(review, { state: 'problem', detail: 'See the message above.' });

  return [
    { id: 'apply', title: 'Apply', state: v ? 'done' : 'now', detail: v ? 'Received.' : 'Confirm you are 18 or older.' },
    { id: 'authorize', title: 'Allow the background check', state: signed ? 'done' : v ? 'now' : 'later',
      detail: signed ? 'Signed.' : 'Read the disclosure and sign with your full legal name.' },
    identity,
    background,
    review,
  ];
}

/** "Friday, December 5" from an ISO date or timestamp, in the reader's time zone. */
export function longDate(iso: string): string {
  const date = /^\d{4}-\d{2}-\d{2}$/.test(iso) ? new Date(`${iso}T12:00:00`) : new Date(iso);
  return date.toLocaleDateString('en-US', { weekday: 'long', month: 'long', day: 'numeric' });
}

export type BookingAction = 'pay' | 'check_in' | 'check_out' | 'confirm' | 'tip' | 'cancel';

/** What this person can do with the booking right now. */
export function bookingActions(b: Booking, role: 'customer' | 'cleaner', jobStatus: string): BookingAction[] {
  if (b.cancelled_by || jobStatus === 'cancelled') return [];
  const paid = b.payment_status === 'paid';
  const canTip = role === 'customer' && paid && !!b.checked_out_at && b.tip_cents === 0;
  if (jobStatus === 'booked') {
    if (role === 'customer') return paid ? ['cancel'] : ['pay', 'cancel'];
    return paid ? ['check_in', 'cancel'] : ['cancel'];
  }
  if (jobStatus === 'in_progress') return role === 'cleaner' ? ['check_out'] : [];
  if (jobStatus === 'awaiting_confirmation') return role === 'customer' ? (canTip ? ['confirm', 'tip'] : ['confirm']) : [];
  if (jobStatus === 'completed') return canTip ? ['tip'] : [];
  return [];
}

/** One sentence on where the booking stands, written for the person reading it. */
export function bookingSummary(b: Booking, role: 'customer' | 'cleaner', jobStatus: string): string {
  const day = longDate(b.starts_on);
  if (b.cancelled_by) {
    const who = b.cancelled_by === role ? 'You' : role === 'customer' ? 'Your cleaner' : 'The customer';
    return b.payment_status === 'refunded' ? `${who} cancelled. The refund goes back to the card used.` : `${who} cancelled this booking.`;
  }
  if (role === 'customer') {
    if (jobStatus === 'booked') return b.payment_status === 'paid' ? `Paid. Your cleaner comes on ${day}.` : `Pay to confirm your booking for ${day}. Your cleaner cannot start until you do.`;
    if (jobStatus === 'in_progress') return 'Your cleaner checked in and is working now.';
    if (jobStatus === 'awaiting_confirmation') return 'Your cleaner says the job is done. Confirm to release their pay. If you do nothing, it is confirmed automatically 48 hours after they checked out.';
    if (jobStatus === 'completed') return 'Done. Your cleaner has been paid.';
  } else {
    if (jobStatus === 'booked') return b.payment_status === 'paid' ? `The customer paid. Check in when you arrive on ${day}.` : 'Waiting for the customer to pay. You can check in once they do.';
    if (jobStatus === 'in_progress') return 'Checked in. Check out when the job is done.';
    if (jobStatus === 'awaiting_confirmation') return 'Checked out. You are paid when the customer confirms, or automatically after 48 hours.';
    if (jobStatus === 'completed') return b.payout_status === 'sent' ? 'Done. Your pay is on its way to your bank.' : 'Done. Your pay is sent once your payout setup is finished.';
  }
  return '';
}

/** Tip choices as a share of the price, rounded to whole dollars, at least $1. */
export function tipOptions(priceCents: number): number[] {
  return [15, 20, 25].map((pct) => Math.max(100, Math.round((priceCents * pct) / 100 / 100) * 100));
}
