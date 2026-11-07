import assert from 'node:assert/strict';
import { describe, it } from 'node:test';

import type { Lookup } from './api';
import { FRESH_MS, LookupCache } from './lookup-cache';

const info = (status: string): Lookup => ({
  status,
  ready: false,
  serviceType: 'deep',
  preferredDate: '2026-12-03',
  reviewSubmitted: false,
  issueSubmitted: false,
  issueStatus: null,
});

function setup() {
  let clock = 0;
  const asked: string[] = [];
  const cache = new LookupCache(
    async (token) => {
      asked.push(token);
      return info('pending');
    },
    () => clock,
  );
  return { cache, asked, tick: (ms: number) => (clock += ms) };
}

describe('status lookups', () => {
  it('reuses a recent answer when a screen is visited again', async () => {
    const { cache, asked } = setup();
    for (let visit = 0; visit < 5; visit += 1) await Promise.all(['a', 'b', 'c'].map((t) => cache.get(t)));
    assert.equal(asked.length, 3);
  });

  it('asks again once the answer is old', async () => {
    const { cache, asked, tick } = setup();
    await cache.get('a');
    tick(FRESH_MS);
    await cache.get('a');
    assert.equal(asked.length, 2);
  });

  it('always asks on pull-to-refresh', async () => {
    const { cache, asked } = setup();
    await cache.get('a');
    await cache.get('a', true);
    assert.equal(asked.length, 2);
  });

  it('asks again after the answer is forgotten, and does not keep failures', async () => {
    const { cache, asked } = setup();
    await cache.get('a');
    cache.forget('a');
    assert.equal(cache.peek('a'), null);
    await cache.get('a');
    assert.equal(asked.length, 2);

    const failing = new LookupCache(async () => {
      throw new Error('offline');
    });
    await assert.rejects(failing.get('x'));
    assert.equal(failing.peek('x'), null);
  });
});
