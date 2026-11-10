import assert from 'node:assert/strict';
import { describe, it } from 'node:test';

import { ApiError, isGone, lookup, sendIssue, sendRequest, sendReview } from './api';
import type { RequestDraft } from './validation';
import { statusCopy } from './status';

const draft: RequestDraft = {
  service: 'deep',
  date: '2026-12-03',
  time: 'afternoon',
  name: '  Pat   Customer ',
  email: ' Pat@Example.com ',
  area: 'Silver Spring',
  notes: 'Two cats',
  consent: true,
};

type Call = { url: string; body: Record<string, unknown> };

function fake(status: number, payload: unknown, calls: Call[] = []): typeof fetch {
  return (async (url: string, init: RequestInit) => {
    calls.push({ url, body: JSON.parse(String(init.body)) });
    return new Response(typeof payload === 'string' ? payload : JSON.stringify(payload), { status });
  }) as unknown as typeof fetch;
}

describe('sending a request', () => {
  it('sends what the server expects, cleaned up', async () => {
    const calls: Call[] = [];
    const result = await sendRequest(draft, fake(201, { ok: true, reference: 'ABC123', feedbackToken: 'tok' }, calls));
    assert.deepEqual(result, { reference: 'ABC123', token: 'tok' });
    assert.match(calls[0].url, /\/api\/service-requests$/);
    assert.deepEqual(calls[0].body, {
      fullName: 'Pat Customer',
      email: 'pat@example.com',
      area: 'Silver Spring',
      serviceType: 'deep',
      preferredDate: '2026-12-03',
      preferredTime: 'afternoon',
      notes: 'Two cats',
      consent: true,
    });
  });

  it('refuses to send an incomplete draft without calling the server', async () => {
    let called = false;
    const spy = (async () => {
      called = true;
      return new Response('{}');
    }) as unknown as typeof fetch;
    await assert.rejects(sendRequest({ ...draft, date: null }, spy), (e: unknown) => e instanceof ApiError && e.kind === 'client');
    assert.equal(called, false);
  });

  it("shows the server's own message for a rejected request", async () => {
    await assert.rejects(
      sendRequest(draft, fake(400, { ok: false, error: 'Preferred date must be today or later.' })),
      (e: unknown) => e instanceof ApiError && e.kind === 'client' && /today or later/.test(e.message),
    );
    await assert.rejects(
      sendRequest(draft, fake(429, { ok: false, error: 'Too many submissions. Please try again later.' })),
      (e: unknown) => e instanceof ApiError && e.status === 429 && /Too many/.test(e.message),
    );
  });

  it('hides server failures behind a plain message', async () => {
    await assert.rejects(
      sendRequest(draft, fake(500, { ok: false, error: 'Traceback: storage driver said the table is locked' })),
      (e: unknown) => e instanceof ApiError && e.kind === 'server' && !/Traceback|storage driver/.test(e.message),
    );
    await assert.rejects(sendRequest(draft, fake(502, '<html>Bad gateway</html>')), (e: unknown) => e instanceof ApiError && e.kind === 'server');
  });

  it('reports a network failure in plain words', async () => {
    const offline = (async () => {
      throw new TypeError('Network request failed');
    }) as unknown as typeof fetch;
    await assert.rejects(sendRequest(draft, offline), (e: unknown) => e instanceof ApiError && e.kind === 'network' && /connection/.test(e.message));
  });

  it('treats a reply without a reference as a server problem', async () => {
    await assert.rejects(sendRequest(draft, fake(201, { ok: true })), (e: unknown) => e instanceof ApiError && e.kind === 'server');
  });
});

describe('looking up and giving feedback', () => {
  it('reads the status', async () => {
    const calls: Call[] = [];
    const info = await lookup(
      'tok',
      fake(200, { ok: true, ready: true, status: 'completed', serviceType: 'routine', preferredDate: '2026-12-03', reviewSubmitted: false, issueSubmitted: true, issueStatus: 'open' }, calls),
    );
    assert.equal(info.ready, true);
    assert.equal(info.issueStatus, 'open');
    assert.deepEqual(calls[0].body, { action: 'lookup', token: 'tok' });
  });

  it('knows when the private link is gone', async () => {
    await assert.rejects(lookup('tok', fake(404, { ok: false, error: 'That private feedback link is invalid.' })), (e: unknown) => isGone(e));
    assert.equal(isGone(new Error('x')), false);
  });

  it('sends a review and an issue with consent', async () => {
    const calls: Call[] = [];
    await sendReview('tok', 5, ' Spotless   kitchen ', fake(201, { ok: true }, calls));
    await sendIssue('tok', 'A mug was chipped', fake(201, { ok: true }, calls));
    assert.deepEqual(calls[0].body, { action: 'review', token: 'tok', rating: 5, message: 'Spotless kitchen', consent: true });
    assert.deepEqual(calls[1].body, { action: 'issue', token: 'tok', message: 'A mug was chipped', consent: true });
  });
});

describe('status wording never overpromises', () => {
  it('does not call an approval a booking', () => {
    for (const status of ['pending', 'approved', 'declined', 'completed', 'cancelled', 'something-new']) {
      const copy = statusCopy(status);
      assert.ok(copy.label.length > 0 && copy.detail.length > 0);
      assert.doesNotMatch(`${copy.label} ${copy.detail}`.toLowerCase(), /\bconfirmed\b(?!\s+booking)|\bbooked\b(?!\s+until)/);
    }
    assert.match(statusCopy('approved').detail, /isn't a confirmed booking/);
  });
});
