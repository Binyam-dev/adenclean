import assert from 'node:assert/strict';
import { describe, it } from 'node:test';

import {
  DECLINED_KEY,
  ENABLED_KEY,
  PENDING_KEY,
  decline,
  disable,
  enable,
  getState,
  registerNew,
  retryPending,
  shouldOffer,
  type Permission,
  type PushDeps,
} from './push-core';

function fake(over: Partial<{ supported: boolean; permission: Permission; askResult: Permission; token: string | null; failFor: string[] }> = {}) {
  const o = { supported: true, permission: 'undetermined' as Permission, askResult: 'granted' as Permission, token: 'ExponentPushToken[abcdefghijkl]', failFor: [] as string[], ...over };
  const store = new Map<string, string>();
  const calls = { register: [] as string[], unregister: [] as string[], asked: 0 };
  const deps: PushDeps = {
    supported: o.supported,
    getPermission: async () => o.permission,
    askPermission: async () => {
      calls.asked += 1;
      o.permission = o.askResult;
      return o.askResult;
    },
    getPushToken: async () => o.token,
    flags: {
      get: async (k) => store.get(k) ?? null,
      set: async (k, v) => void store.set(k, v),
      remove: async (k) => void store.delete(k),
    },
    register: async (t) => {
      calls.register.push(t);
    },
    unregister: async (t) => {
      calls.unregister.push(t);
      if (o.failFor.includes(t)) throw new Error('offline');
    },
    saved: async () => [
      { reference: 'A1', token: 'tokA' },
      { reference: 'B2', token: 'tokB' },
    ],
  };
  return { deps, store, calls, o };
}

describe('push choices', () => {
  it('offers only on a real phone, before any answer', async () => {
    assert.equal(await shouldOffer(fake().deps), true);
    assert.equal(await shouldOffer(fake({ supported: false }).deps), false);
    assert.equal(await shouldOffer(fake({ permission: 'denied' }).deps), false);
  });

  it('never offers again after Not now', async () => {
    const f = fake();
    await decline(f.deps);
    assert.equal(await shouldOffer(f.deps), false);
    assert.equal(f.calls.asked, 0);
  });

  it('asks the system once, then registers every saved request', async () => {
    const f = fake();
    assert.equal(await enable(f.deps), 'on');
    assert.equal(f.calls.asked, 1);
    assert.deepEqual(f.calls.register.sort(), ['tokA', 'tokB']);
    assert.equal(await getState(f.deps), 'on');
    assert.equal(await shouldOffer(f.deps), false);
  });

  it('does not ask again when permission is already granted', async () => {
    const f = fake({ permission: 'granted' });
    assert.equal(await enable(f.deps), 'on');
    assert.equal(f.calls.asked, 0);
  });

  it('reports blocked when the system says no, and registers nothing', async () => {
    const f = fake({ askResult: 'denied' });
    assert.equal(await enable(f.deps), 'blocked');
    assert.equal(f.calls.register.length, 0);
    assert.equal(await getState(f.deps), 'off');
  });

  it('reports failed when no token can be had', async () => {
    const f = fake({ token: null });
    assert.equal(await enable(f.deps), 'failed');
    assert.equal(await getState(f.deps), 'off');
  });

  it('a new request registers only while notifications are on', async () => {
    const f = fake();
    assert.equal(await registerNew(f.deps, { token: 'tokC' }), false);
    await enable(f.deps);
    f.calls.register.length = 0;
    assert.equal(await registerNew(f.deps, { token: 'tokC' }), true);
    assert.deepEqual(f.calls.register, ['tokC']);
  });

  it('registering a new request never throws, even when the server errors', async () => {
    const f = fake();
    await enable(f.deps);
    f.deps.register = async () => {
      throw new Error('400 from an older server');
    };
    assert.equal(await registerNew(f.deps, { token: 'tokC' }), false);
  });

  it('shows blocked when the person later turns notifications off in system settings', async () => {
    const f = fake();
    await enable(f.deps);
    f.o.permission = 'denied';
    assert.equal(await getState(f.deps), 'blocked');
  });

  it('turning off removes the phone from every request and is not offered again', async () => {
    const f = fake();
    await enable(f.deps);
    assert.deepEqual(await disable(f.deps), { pending: 0 });
    assert.deepEqual(f.calls.unregister.sort(), ['tokA', 'tokB']);
    assert.equal(f.store.get(ENABLED_KEY), undefined);
    assert.equal(f.store.get(DECLINED_KEY), '1');
    assert.equal(f.store.has(PENDING_KEY), false);
  });

  it('keeps failed removals and retries them at next launch', async () => {
    const f = fake({ failFor: ['tokB'] });
    await enable(f.deps);
    assert.deepEqual(await disable(f.deps), { pending: 1 });
    assert.equal(f.store.get(PENDING_KEY), JSON.stringify(['B2']));
    f.o.failFor = [];
    f.calls.unregister.length = 0;
    await retryPending(f.deps);
    assert.deepEqual(f.calls.unregister, ['tokB']);
    assert.equal(f.store.has(PENDING_KEY), false);
  });

  it('with no token to remove, everything stays pending', async () => {
    const f = fake();
    await enable(f.deps);
    f.o.token = null;
    assert.deepEqual(await disable(f.deps), { pending: 2 });
    f.o.token = 'ExponentPushToken[abcdefghijkl]';
    await retryPending(f.deps);
    assert.equal(f.store.has(PENDING_KEY), false);
    assert.equal(f.calls.unregister.length, 2);
  });

  it('drops pending removals for requests no longer on the phone', async () => {
    const f = fake();
    f.store.set(PENDING_KEY, JSON.stringify(['GONE']));
    await retryPending(f.deps);
    assert.equal(f.store.has(PENDING_KEY), false);
    assert.equal(f.calls.unregister.length, 0);
  });

  it('does nothing on unsupported devices', async () => {
    const f = fake({ supported: false });
    assert.equal(await getState(f.deps), 'unsupported');
    assert.equal(await enable(f.deps), 'failed');
    await retryPending(f.deps);
    assert.equal(f.calls.asked, 0);
  });
});
