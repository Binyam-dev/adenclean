import assert from 'node:assert/strict';
import { describe, it } from 'node:test';

import { SUPPORT_EMAIL } from './config';
import { blockedLine, canSubmitReport, REPORT_DETAIL_MAX, REPORT_REASONS, reportThanks } from './moderation';
import { Client } from './v1';

type Call = { url: string; method: string; body: unknown };

function recorder(payload: unknown, status = 200, calls: Call[] = []): typeof fetch {
  return (async (url: string, init: RequestInit) => {
    calls.push({ url, method: String(init.method), body: init.body ? JSON.parse(String(init.body)) : null });
    return new Response(JSON.stringify(payload), { status });
  }) as unknown as typeof fetch;
}

describe('report form rules', () => {
  it('needs a listed reason and a detail within the limit', () => {
    assert.equal(canSubmitReport(null, ''), false);
    assert.equal(canSubmitReport('rude', ''), false);
    assert.equal(canSubmitReport('spam', ''), true);
    assert.equal(canSubmitReport('spam', 'x'.repeat(REPORT_DETAIL_MAX)), true);
    assert.equal(canSubmitReport('spam', 'x'.repeat(REPORT_DETAIL_MAX + 1)), false);
  });

  it('offers exactly the reasons the server accepts, with no duplicates', () => {
    assert.deepEqual(REPORT_REASONS.map((r) => r.id).sort(), ['fake', 'harassment', 'off_platform', 'other', 'spam', 'unsafe']);
  });

  it('promises a 24-hour review and shows the support address', () => {
    assert.match(reportThanks(false), /within 24 hours/);
    assert.ok(reportThanks(false).includes(SUPPORT_EMAIL));
    assert.match(reportThanks(true), /already reported/);
  });

  it('shows a blocked person by name and tolerates a bad date', () => {
    assert.match(blockedLine('Hana', '2026-11-09T12:00:00Z'), /^Hana, blocked Nov \d+$/);
    assert.equal(blockedLine('Hana', 'not a date'), 'Hana');
  });
});

describe('report and block calls', () => {
  it('sends the report with the right target and omits an empty note', async () => {
    const calls: Call[] = [];
    const client = new Client('t', recorder({ ok: true, merged: false, reportId: 'r1' }, 201, calls));
    assert.deepEqual(await client.report('offer', 'o1', 'unsafe', '   '), { merged: false });
    assert.deepEqual(calls[0].body, { targetKind: 'offer', targetId: 'o1', reason: 'unsafe' });
    await client.report('job', 'j1', 'spam', ' rude notes ');
    assert.deepEqual(calls[1].body, { targetKind: 'job', targetId: 'j1', reason: 'spam', detail: 'rude notes' });
    assert.match(calls[0].url, /\/api\/v1\/reports$/);
  });

  it('reports a merged duplicate', async () => {
    const client = new Client('t', recorder({ ok: true, merged: true, reportId: 'r1' }));
    assert.deepEqual(await client.report('job', 'j1', 'spam', ''), { merged: true });
  });

  it('blocks through a job or an offer and returns the block id', async () => {
    const calls: Call[] = [];
    const client = new Client('t', recorder({ ok: true, blockId: 'b1' }, 200, calls));
    assert.equal(await client.block('job', 'j1'), 'b1');
    assert.equal(await client.block('offer', 'o1'), 'b1');
    assert.match(calls[0].url, /\/api\/v1\/jobs\/j1\/block$/);
    assert.match(calls[1].url, /\/api\/v1\/offers\/o1\/block$/);
  });

  it('lists and removes blocks', async () => {
    const calls: Call[] = [];
    const client = new Client('t', recorder({ ok: true, blocks: [{ id: 'b1', name: 'Hana', created_at: 'x' }] }, 200, calls));
    assert.deepEqual((await client.blocks()).map((b) => b.name), ['Hana']);
    await client.unblock('b1');
    assert.match(calls[1].url, /\/api\/v1\/blocks\/b1\/remove$/);
    assert.equal(calls[1].method, 'POST');
  });
});
