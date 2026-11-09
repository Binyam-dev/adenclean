import assert from 'node:assert/strict';
import { describe, it } from 'node:test';

import { bookingActions, bookingSummary, tipOptions, vettingSteps } from './steps';
import { Client, type Booking, type Vetting } from './v1';

const fresh: Vetting = { status: 'applied', identity_status: 'not_started', background_status: 'not_started',
  consent_at: null, dispute_deadline: null, dispute_open: 0 };
const states = (v: Vetting | null) => vettingSteps(v).map((s) => `${s.id}:${s.state}`);

const booking = (over: Partial<Booking> = {}): Booking => ({ job_id: 'j', price_cents: 15_000, tip_cents: 0,
  payment_status: 'unpaid', payout_status: 'none', starts_on: '2026-12-05', checked_in_at: null,
  checked_out_at: null, confirmed_at: null, cancelled_by: null, ...over });

describe('vetting checklist', () => {
  it('opens no check before the disclosure is signed', () => {
    assert.deepEqual(states(null), ['apply:now', 'authorize:later', 'identity:later', 'background:later', 'review:later']);
    assert.deepEqual(states(fresh), ['apply:done', 'authorize:now', 'identity:later', 'background:later', 'review:later']);
  });

  it('offers both checks once signed and tracks each one', () => {
    const signed = { ...fresh, consent_at: '2026-11-04T10:00:00Z' };
    assert.deepEqual(states(signed).slice(2, 4), ['identity:now', 'background:now']);
    const mid = { ...signed, identity_status: 'failed' as const, background_status: 'invited' as const };
    assert.deepEqual(states(mid).slice(2, 4), ['identity:problem', 'background:waiting']);
    const review = { ...signed, status: 'in_review' as const, identity_status: 'verified' as const, background_status: 'consider' as const };
    assert.deepEqual(states(review).slice(2), ['identity:done', 'background:done', 'review:waiting']);
  });

  it('never shows the report result to the applicant', () => {
    const consider = vettingSteps({ ...fresh, consent_at: 'x', background_status: 'consider' })[3];
    const clear = vettingSteps({ ...fresh, consent_at: 'x', background_status: 'clear' })[3];
    assert.equal(consider.detail, clear.detail);
  });
});

describe('booking actions', () => {
  it('follows pay, check in, check out, confirm, tip', () => {
    assert.deepEqual(bookingActions(booking(), 'customer', 'booked'), ['pay', 'cancel']);
    assert.deepEqual(bookingActions(booking(), 'cleaner', 'booked'), ['cancel']);
    const paid = booking({ payment_status: 'paid' });
    assert.deepEqual(bookingActions(paid, 'cleaner', 'booked'), ['check_in', 'cancel']);
    assert.deepEqual(bookingActions(paid, 'customer', 'in_progress'), []);
    assert.deepEqual(bookingActions(paid, 'cleaner', 'in_progress'), ['check_out']);
    const out = booking({ payment_status: 'paid', checked_out_at: '2026-12-05T15:00:00Z' });
    assert.deepEqual(bookingActions(out, 'customer', 'awaiting_confirmation'), ['confirm', 'tip']);
    assert.deepEqual(bookingActions(out, 'cleaner', 'awaiting_confirmation'), []);
    assert.deepEqual(bookingActions(out, 'customer', 'completed'), ['tip']);
    assert.deepEqual(bookingActions({ ...out, tip_cents: 2_000 }, 'customer', 'completed'), []);
  });

  it('offers nothing after a cancellation and says who cancelled', () => {
    const gone = booking({ payment_status: 'refunded', cancelled_by: 'cleaner' });
    assert.deepEqual(bookingActions(gone, 'customer', 'cancelled'), []);
    assert.match(bookingSummary(gone, 'customer', 'cancelled'), /^Your cleaner cancelled\. The refund/);
    assert.match(bookingSummary(gone, 'cleaner', 'cancelled'), /^You cancelled/);
  });

  it('suggests whole-dollar tips of at least $1', () => {
    assert.deepEqual(tipOptions(15_000), [2_300, 3_000, 3_800]);
    assert.deepEqual(tipOptions(300), [100, 100, 100]);
  });
});

describe('vetting and booking calls', () => {
  it('treats a missing application as null and a missing payout account as "none"', async () => {
    const notFound = (async () => new Response(JSON.stringify({ ok: false, error: 'nope' }), { status: 404 })) as unknown as typeof fetch;
    const client = new Client('t', notFound);
    assert.equal(await client.vetting(), null);
    assert.equal(await client.payoutState(), 'none');
    const off = (async () => new Response(JSON.stringify({ ok: false, error: 'off' }), { status: 503 })) as unknown as typeof fetch;
    assert.equal(await new Client('t', off).payoutState(), 'off');
  });

  it('reads the refund and late fee from a cancellation', async () => {
    const urls: string[] = [];
    const ok = (async (url: string) => {
      urls.push(url);
      return new Response(JSON.stringify({ ok: true, refundCents: 11_250, cleanerFeeCents: 3_750 }), { status: 200 });
    }) as unknown as typeof fetch;
    assert.deepEqual(await new Client('t', ok).cancelBooking('j1'), { refundCents: 11_250, cleanerFeeCents: 3_750 });
    assert.match(urls[0], /\/api\/v1\/jobs\/j1\/cancel-booking$/);
  });
});
