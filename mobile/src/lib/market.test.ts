import assert from 'node:assert/strict';
import { describe, it } from 'node:test';

import { ApiError } from './api';
import { checkCode, checkPrice, checkZip, formatCents, myTurn, parseDollars, payoutAfterFee } from './market';
import { Client, isSignedOut } from './v1';

type Call = { url: string; method: string; auth: string | null; body: unknown };

function fake(status: number, payload: unknown, calls: Call[] = []): typeof fetch {
  return (async (url: string, init: RequestInit) => {
    const headers = (init.headers ?? {}) as Record<string, string>;
    calls.push({ url, method: String(init.method), auth: headers.Authorization ?? null, body: init.body ? JSON.parse(String(init.body)) : null });
    return new Response(JSON.stringify(payload), { status });
  }) as unknown as typeof fetch;
}

describe('money', () => {
  it('parses typed dollars into whole cents', () => {
    assert.equal(parseDollars('120'), 12_000);
    assert.equal(parseDollars('$120.5'), 12_050);
    assert.equal(parseDollars('1,250.05'), 125_005);
    for (const bad of ['', 'abc', '12.345', '-5', '1e3']) assert.equal(parseDollars(bad), null, bad);
  });

  it('formats cents without floating point drift', () => {
    assert.equal(formatCents(12_345), '$123.45');
    assert.equal(formatCents(5), '$0.05');
    assert.equal(formatCents(125_000), '$1,250.00');
    assert.equal(formatCents(null), '');
  });

  it('checks prices, ZIP codes and sign-in codes', () => {
    assert.equal(checkPrice('120'), null);
    assert.match(String(checkPrice('5')), /from \$20\.00/);
    assert.equal(checkZip('20910'), null);
    assert.ok(checkZip('2091'));
    assert.equal(checkCode('123456'), null);
    assert.ok(checkCode('12345'));
  });

  it('shows the payout after the fee exactly as the server computes it', () => {
    // Server: (12345 * 1500 + 5000) // 10000 = 1852
    assert.deepEqual(payoutAfterFee(12_345, 1500), { fee: 1_852, payout: 10_493 });
    assert.deepEqual(payoutAfterFee(10_000, 1500), { fee: 1_500, payout: 8_500 });
  });

  it('knows whose turn it is on an offer', () => {
    assert.equal(myTurn({ status: 'pending', awaiting: 'customer' }, 'customer'), true);
    assert.equal(myTurn({ status: 'countered', awaiting: 'cleaner' }, 'customer'), false);
    assert.equal(myTurn({ status: 'accepted', awaiting: 'customer' }, 'customer'), false);
  });
});

describe('marketplace client', () => {
  it('sends the session token and the body the server expects', async () => {
    const calls: Call[] = [];
    const client = new Client('tok123', fake(201, { ok: true, offer: { id: 'o1' } }, calls));
    const offer = await client.sendOffer('job1', 15_000, '  Happy to help  ');
    assert.equal(offer.id, 'o1');
    assert.match(calls[0].url, /\/api\/v1\/jobs\/job1\/offers$/);
    assert.equal(calls[0].auth, 'Bearer tok123');
    assert.deepEqual(calls[0].body, { priceCents: 15_000, message: 'Happy to help' });
  });

  it('sends no token when signed out and lowercases the email', async () => {
    const calls: Call[] = [];
    await new Client(null, fake(200, { ok: true }, calls)).requestCode('  Pat@Example.COM ');
    assert.equal(calls[0].auth, null);
    assert.deepEqual(calls[0].body, { email: 'pat@example.com' });
  });

  it('turns server answers into readable errors', async () => {
    await assert.rejects(new Client('t', fake(409, { ok: false, error: 'This offer is closed' })).answer('o1', 'accept'),
      (e: unknown) => e instanceof ApiError && e.message === 'This offer is closed');
    await assert.rejects(new Client('t', fake(401, { ok: false, error: 'Sign in to continue.' })).me(),
      (e: unknown) => isSignedOut(e));
    await assert.rejects(new Client('t', fake(500, 'oops')).myJobs(), (e: unknown) => e instanceof ApiError && e.kind === 'server');
    await assert.rejects(new Client('t', fake(503, { ok: false, error: 'Email sign-in is not turned on yet.' })).requestCode('a@b.co'),
      (e: unknown) => e instanceof ApiError && e.message === 'Email sign-in is not turned on yet.');
  });

  it('never calls the global fetch with the client as `this` (browsers reject that)', async () => {
    const realFetch = globalThis.fetch;
    let sawThis: unknown = 'unset';
    globalThis.fetch = function (this: unknown) {
      sawThis = this;
      if (this !== undefined && this !== globalThis) throw new TypeError('Illegal invocation');
      return Promise.resolve(new Response(JSON.stringify({ ok: true, user: { id: 'u' } }), { status: 200 }));
    } as typeof fetch;
    try {
      const user = await new Client('t').me();
      assert.equal(user.id, 'u');
      assert.ok(sawThis === undefined || sawThis === globalThis);
    } finally {
      globalThis.fetch = realFetch;
    }
  });

  it('reports a network failure plainly', async () => {
    const offline = (async () => {
      throw new TypeError('fetch failed');
    }) as unknown as typeof fetch;
    await assert.rejects(new Client('t', offline).openJobs(), (e: unknown) => e instanceof ApiError && e.kind === 'network');
  });
});
