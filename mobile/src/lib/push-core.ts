// Notification choices, kept free of any phone-only imports so they can be tested in Node.
// push.ts wires this to the real permission prompt, token and storage.
//
// Rules (docs/SPEC-push-notifications.md): ask only after the person has sent a request and
// agreed in the app; "Not now" is remembered and never asked again; turning notifications off
// removes this phone from every saved request, and anything that fails is retried at next launch.

export type Permission = 'granted' | 'denied' | 'undetermined';
export type PushState = 'unsupported' | 'off' | 'on' | 'blocked';
export type EnableResult = 'on' | 'blocked' | 'failed';

export type PushDeps = {
  supported: boolean; // a real phone (not web or a simulator)
  getPermission(): Promise<Permission>;
  askPermission(): Promise<Permission>;
  getPushToken(): Promise<string | null>;
  flags: { get(key: string): Promise<string | null>; set(key: string, value: string): Promise<void>; remove(key: string): Promise<void> };
  register(requestToken: string, pushToken: string): Promise<void>;
  unregister(requestToken: string, pushToken: string): Promise<void>;
  saved(): Promise<{ reference: string; token: string }[]>;
};

export const ENABLED_KEY = 'adenclean.push.on';
export const DECLINED_KEY = 'adenclean.push.declined';
export const PENDING_KEY = 'adenclean.push.pending';
const BATCH = 5;

export async function getState(d: PushDeps): Promise<PushState> {
  if (!d.supported) return 'unsupported';
  if ((await d.flags.get(ENABLED_KEY)) !== '1') return 'off';
  return (await d.getPermission()) === 'granted' ? 'on' : 'blocked';
}

/** True when the app may show its own "turn on notifications?" card. */
export async function shouldOffer(d: PushDeps): Promise<boolean> {
  if (!d.supported) return false;
  if ((await d.flags.get(ENABLED_KEY)) === '1' || (await d.flags.get(DECLINED_KEY)) === '1') return false;
  return (await d.getPermission()) !== 'denied';
}

async function eachInBatches<T>(items: T[], run: (item: T) => Promise<unknown>): Promise<void> {
  for (let i = 0; i < items.length; i += BATCH) {
    await Promise.allSettled(items.slice(i, i + BATCH).map(run));
  }
}

/** Asks the system for permission (once), then registers this phone for every saved request. */
export async function enable(d: PushDeps): Promise<EnableResult> {
  if (!d.supported) return 'failed';
  let permission = await d.getPermission();
  if (permission === 'undetermined') permission = await d.askPermission();
  if (permission !== 'granted') return 'blocked';
  const pushToken = await d.getPushToken();
  if (!pushToken) return 'failed';
  await d.flags.set(ENABLED_KEY, '1');
  await d.flags.remove(DECLINED_KEY);
  // Best effort: an older server answers with an error, and the next launch of a newer one is fine.
  await eachInBatches(await d.saved(), (item) => d.register(item.token, pushToken));
  return 'on';
}

/** A request saved while notifications are on. Never throws. */
export async function registerNew(d: PushDeps, item: { token: string }): Promise<boolean> {
  try {
    if ((await getState(d)) !== 'on') return false;
    const pushToken = await d.getPushToken();
    if (!pushToken) return false;
    await d.register(item.token, pushToken);
    return true;
  } catch {
    return false;
  }
}

export async function decline(d: PushDeps): Promise<void> {
  await d.flags.set(DECLINED_KEY, '1');
}

async function readPending(d: PushDeps): Promise<string[]> {
  try {
    const parsed = JSON.parse((await d.flags.get(PENDING_KEY)) ?? '[]');
    return Array.isArray(parsed) ? parsed.filter((v): v is string => typeof v === 'string') : [];
  } catch {
    return [];
  }
}

async function writePending(d: PushDeps, refs: string[]): Promise<void> {
  if (refs.length === 0) await d.flags.remove(PENDING_KEY);
  else await d.flags.set(PENDING_KEY, JSON.stringify(refs));
}

async function unregisterAll(d: PushDeps, refs: string[]): Promise<string[]> {
  const items = (await d.saved()).filter((s) => refs.includes(s.reference));
  const pushToken = await d.getPushToken().catch(() => null);
  if (!pushToken) return items.map((s) => s.reference); // try again later
  const failed: string[] = [];
  await eachInBatches(items, async (item) => {
    try {
      await d.unregister(item.token, pushToken);
    } catch {
      failed.push(item.reference);
    }
  });
  return failed;
}

/** Turns notifications off: this phone leaves every saved request. Failures are retried later. */
export async function disable(d: PushDeps): Promise<{ pending: number }> {
  await d.flags.remove(ENABLED_KEY);
  await d.flags.set(DECLINED_KEY, '1');
  const all = (await d.saved()).map((s) => s.reference);
  const failed = await unregisterAll(d, all);
  await writePending(d, failed);
  return { pending: failed.length };
}

/** At launch: finish any removals that failed earlier. Never throws. */
export async function retryPending(d: PushDeps): Promise<void> {
  try {
    if (!d.supported) return;
    const pending = await readPending(d);
    if (pending.length === 0) return;
    await writePending(d, await unregisterAll(d, pending));
  } catch {
    // Try again next launch.
  }
}
