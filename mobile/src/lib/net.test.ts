import assert from 'node:assert/strict';
import { afterEach, beforeEach, describe, it } from 'node:test';

import { ApiError, lookup, sendRequest } from './api';
import { isSlow, retry, shouldRetry, subscribeSlow, trackSlow } from './net';
import type { RequestDraft } from './validation';

const draft: RequestDraft = {
  service: 'deep', date: '2026-12-03', time: 'afternoon', name: 'Pat', email: 'pat@example.com',
  area: 'Silver Spring', notes: '', consent: true,
};
const TOKEN = 'A'.repeat(43);
const original = { ...retry };

/** A fetch that plays back the given outcomes in order: a status, 'network', or a [status, body] pair. */
function script(outcomes: (number | 'network' | [number, unknown])[], calls: { n: number }): typeof fetch {
  return (async () => {
    const next = outcomes[Math.min(calls.n, outcomes.length - 1)];
    calls.n += 1;
    if (next === 'network') throw new TypeError('Network request failed');
    const [status, body] = Array.isArray(next) ? next : [next, { ok: status2ok(next) }];
    return new Response(JSON.stringify(body), { status });
  }) as unknown as typeof fetch;
}
const status2ok = (status: number) => status < 400;

beforeEach(() => {
  retry.delaysMs = [0, 0];
  retry.sleep = async () => undefined;
});
afterEach(() => Object.assign(retry, original));

const goodLookup: [number, unknown] = [200, { ok: true, status: 'pending', ready: false, serviceType: 'deep', preferredDate: '2026-12-03' }];
const goodSend: [number, unknown] = [201, { ok: true, reference: 'REF1', feedbackToken: 'tok' }];

describe('retry rules', () => {
  it('reads retry on a dropped connection and on 502, 503 and 504', () => {
    for (const status of [0, 502, 503, 504]) assert.equal(shouldRetry(status, true, 0), true, String(status));
  });

  it('sending is never retried: any failure can arrive after the server saved it', () => {
    for (const status of [0, 502, 503, 504]) assert.equal(shouldRetry(status, false, 0), false, String(status));
  });

  it('never retries an answer from the app itself, and stops after the allowed attempts', () => {
    for (const status of [200, 201, 400, 404, 409, 429, 500]) assert.equal(shouldRetry(status, true, 0), false, String(status));
    assert.equal(shouldRetry(503, true, 2), false);
  });
});

describe('a sleeping server', () => {
  it('a status check survives two failures and then succeeds', async () => {
    const calls = { n: 0 };
    const result = await lookup(TOKEN, script(['network', 503, goodLookup], calls));
    assert.equal(result.status, 'pending');
    assert.equal(calls.n, 3);
  });

  it('a status check gives up with a plain message after the last attempt', async () => {
    const calls = { n: 0 };
    await assert.rejects(lookup(TOKEN, script(['network'], calls)), (e: unknown) => e instanceof ApiError && e.kind === 'network');
    assert.equal(calls.n, 3);
  });

  it('sending a request is NOT repeated after a 502 or 503 from the gateway', async () => {
    for (const status of [502, 503]) {
      const calls = { n: 0 };
      await assert.rejects(sendRequest(draft, script([status, goodSend], calls)), (e: unknown) => e instanceof ApiError && e.kind === 'server');
      assert.equal(calls.n, 1, String(status));
    }
  });

  it('sending a request is NOT repeated after a dropped connection', async () => {
    const calls = { n: 0 };
    await assert.rejects(sendRequest(draft, script(['network', goodSend], calls)), (e: unknown) => e instanceof ApiError && e.kind === 'network');
    assert.equal(calls.n, 1);
  });

  it('a server error or a bad request is reported at once, not retried', async () => {
    for (const status of [400, 404, 429, 500]) {
      const calls = { n: 0 };
      await assert.rejects(lookup(TOKEN, script([[status, { ok: false, error: 'x' }]], calls)));
      assert.equal(calls.n, 1, String(status));
    }
  });
});

describe('the slow signal', () => {
  it('turns on after the delay, off when the request ends, and counts overlapping requests', async () => {
    retry.slowAfterMs = 20;
    const seen: boolean[] = [];
    const stop = subscribeSlow(() => seen.push(isSlow()));
    const first = trackSlow();
    const second = trackSlow();
    assert.equal(isSlow(), false);
    await new Promise((resolve) => setTimeout(resolve, 60));
    assert.equal(isSlow(), true);
    first();
    assert.equal(isSlow(), true); // the other one is still waiting
    second();
    assert.equal(isSlow(), false);
    stop();
    assert.deepEqual(seen, [true, true, true, false]);
  });

  it('never turns on for a fast request', async () => {
    retry.slowAfterMs = 50;
    const done = trackSlow();
    done();
    await new Promise((resolve) => setTimeout(resolve, 80));
    assert.equal(isSlow(), false);
  });
});
