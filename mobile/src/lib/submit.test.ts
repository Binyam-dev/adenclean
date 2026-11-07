import assert from 'node:assert/strict';
import { describe, it } from 'node:test';

import type { SentRequest } from './api';
import type { SavedRequest } from './storage';
import { keepSent, sendAndKeep } from './submit';

const sent: SentRequest = { reference: 'ABC123', token: 'tok' };
const describeSent = (s: SentRequest): SavedRequest => ({
  reference: s.reference,
  token: s.token,
  createdAt: '2026-11-06T00:00:00.000Z',
  service: 'deep',
  date: '2026-12-03',
  time: 'afternoon',
});
const noWait = async () => {};

describe('sending and keeping a request', () => {
  it('reports success when both steps work', async () => {
    const kept: SavedRequest[] = [];
    const outcome = await sendAndKeep(async () => sent, describeSent, { save: async (i) => void kept.push(i), sleep: noWait });
    assert.deepEqual(outcome, { sent, saved: true });
    assert.equal(kept[0].token, 'tok');
  });

  it('keeps the sent request when the phone cannot save it, without sending again', async () => {
    let sends = 0;
    let saves = 0;
    const outcome = await sendAndKeep(
      async () => {
        sends += 1;
        return sent;
      },
      describeSent,
      {
        save: async () => {
          saves += 1;
          throw new Error('secure storage unavailable');
        },
        sleep: noWait,
      },
    );
    assert.deepEqual(outcome, { sent, saved: false }); // still has the reference and private code
    assert.equal(sends, 1);
    assert.equal(saves, 3);
  });

  it('still throws when the send itself fails, so trying again is safe', async () => {
    let saves = 0;
    await assert.rejects(
      sendAndKeep(
        async () => {
          throw new Error('offline');
        },
        describeSent,
        { save: async () => void (saves += 1), sleep: noWait },
      ),
    );
    assert.equal(saves, 0);
  });

  it('recovers when a later save attempt works', async () => {
    let saves = 0;
    const ok = await keepSent(describeSent(sent), {
      save: async () => {
        saves += 1;
        if (saves < 2) throw new Error('busy');
      },
      sleep: noWait,
    });
    assert.equal(ok, true);
    assert.equal(saves, 2);
  });
});
