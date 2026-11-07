import type { SentRequest } from './api';
import type { SavedRequest } from './storage';

// Sending a request and saving it on the phone are two separate steps. Once the server
// has accepted a request it must never be reported as "not sent": that invites the person
// to send it again (a second record on the server) and throws away the private code they
// need to track the first one.

export type SaveOutcome = { sent: SentRequest; saved: boolean };

type Deps = {
  save: (item: SavedRequest) => Promise<void>;
  attempts?: number;
  waitMs?: number;
  sleep?: (ms: number) => Promise<void>;
};

const pause = (ms: number) => new Promise<void>((resolve) => setTimeout(resolve, ms));

/** Saves an already-sent request on the phone, retrying a few times. Never throws. */
export async function keepSent(item: SavedRequest, deps: Deps): Promise<boolean> {
  const attempts = Math.max(1, deps.attempts ?? 3);
  const sleep = deps.sleep ?? pause;
  for (let attempt = 1; attempt <= attempts; attempt += 1) {
    try {
      await deps.save(item);
      return true;
    } catch {
      if (attempt < attempts) await sleep((deps.waitMs ?? 300) * attempt);
    }
  }
  return false;
}

/**
 * Sends the request, then saves it locally. A failed send throws (nothing reached the
 * server, so trying again is safe). A failed local save does not throw: the caller gets
 * `saved: false` with the reference and private code still in hand.
 */
export async function sendAndKeep(
  send: () => Promise<SentRequest>,
  describe: (sent: SentRequest) => SavedRequest,
  deps: Deps,
): Promise<SaveOutcome> {
  const sent = await send();
  const saved = await keepSent(describe(sent), deps);
  return { sent, saved };
}
