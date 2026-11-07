import type { Lookup } from './api';

// Status lookups are rate-limited per network address on the server (see
// LOOKUP_RATE_LIMIT_MAX_REQUESTS in main.py). The Requests tab shows up to 60 saved
// requests, so looking every one up again on each tab visit, or each time the person
// comes back from a request's detail, spends the allowance in a couple of taps.
//
// Statuses only change when AdenClean reviews a request, so a recent answer is reused for
// screen visits. Pull-to-refresh (force) always asks the server again.

export const FRESH_MS = 5 * 60 * 1000;

type Entry = { info: Lookup; at: number };

export class LookupCache {
  private entries = new Map<string, Entry>();

  constructor(private fetchOne: (token: string) => Promise<Lookup>, private now: () => number = Date.now, private freshMs = FRESH_MS) {}

  /** A recent answer for this token, or null when there is none. */
  peek(token: string): Lookup | null {
    const entry = this.entries.get(token);
    return entry && this.now() - entry.at < this.freshMs ? entry.info : null;
  }

  remember(token: string, info: Lookup): void {
    this.entries.set(token, { info, at: this.now() });
  }

  forget(token: string): void {
    this.entries.delete(token);
  }

  /** Returns a fresh answer when there is one; otherwise asks the server. Errors are not cached. */
  async get(token: string, force = false): Promise<Lookup> {
    if (!force) {
      const recent = this.peek(token);
      if (recent) return recent;
    }
    const info = await this.fetchOne(token);
    this.remember(token, info);
    return info;
  }
}
