import { API_URL } from './config';
import { LookupCache } from './lookup-cache';
import { retry, shouldRetry, trackSlow } from './net';
import { clean, type RequestDraft } from './validation';

export class ApiError extends Error {
  status: number;
  kind: 'network' | 'server' | 'client';
  constructor(kind: 'network' | 'server' | 'client', status: number, message: string) {
    super(message);
    this.kind = kind;
    this.status = status;
  }
}

const NETWORK_MESSAGE = "Can't reach AdenClean. Check your connection and try again.";
const SERVER_MESSAGE = 'Something went wrong on our side. Try again in a moment.';

type Json = Record<string, unknown>;

/** One try. Resolves to the response, or null when the connection failed or timed out. */
async function attemptOnce(path: string, body: Json, fetcher: typeof fetch, timeoutMs: number): Promise<Response | null> {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeoutMs);
  try {
    return await fetcher(`${API_URL}${path}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
      signal: controller.signal,
    });
  } catch {
    return null;
  } finally {
    clearTimeout(timer);
  }
}

/**
 * Sends a JSON POST. `idempotent` is true for reads (the status check), which are safe to
 * repeat; see net.ts for why sending a request is treated differently.
 */
async function post(path: string, body: Json, fetcher: typeof fetch = fetch, idempotent = false): Promise<Json> {
  const timeoutMs = idempotent ? retry.readTimeoutMs : retry.writeTimeoutMs;
  const done = trackSlow();
  let response: Response | null;
  try {
    for (let attempt = 0; ; attempt += 1) {
      response = await attemptOnce(path, body, fetcher, timeoutMs);
      if (!shouldRetry(response ? response.status : 0, idempotent, attempt)) break;
      await retry.sleep(retry.delaysMs[attempt]);
    }
  } finally {
    done();
  }
  if (response === null) throw new ApiError('network', 0, NETWORK_MESSAGE);

  let payload: Json = {};
  try {
    payload = (await response.json()) as Json;
  } catch {
    // Not JSON (for example a proxy error page); fall through to the status check.
  }

  if (!response.ok || payload.ok === false) {
    const message = typeof payload.error === 'string' ? payload.error : '';
    if (response.status >= 500 || !message) throw new ApiError('server', response.status, SERVER_MESSAGE);
    throw new ApiError('client', response.status, message);
  }
  return payload;
}

export type SentRequest = { reference: string; token: string };

export async function sendRequest(draft: RequestDraft, fetcher?: typeof fetch): Promise<SentRequest> {
  if (!draft.service || !draft.date || !draft.time) {
    throw new ApiError('client', 400, 'Choose a service, day and time first.');
  }
  const payload = await post(
    '/api/service-requests',
    {
      fullName: clean(draft.name),
      email: clean(draft.email).toLowerCase(),
      area: clean(draft.area),
      serviceType: draft.service,
      preferredDate: draft.date,
      preferredTime: draft.time,
      notes: clean(draft.notes, true),
      consent: draft.consent === true,
    },
    fetcher,
  );
  if (typeof payload.reference !== 'string' || typeof payload.feedbackToken !== 'string') {
    throw new ApiError('server', 200, SERVER_MESSAGE);
  }
  return { reference: payload.reference, token: payload.feedbackToken };
}

export type RequestStatus = 'pending' | 'approved' | 'declined' | 'completed' | 'cancelled';

export type Lookup = {
  status: RequestStatus | string;
  ready: boolean;
  serviceType: string;
  preferredDate: string;
  reviewSubmitted: boolean;
  issueSubmitted: boolean;
  issueStatus: string | null;
};

export async function lookup(token: string, fetcher?: typeof fetch): Promise<Lookup> {
  const p = await post('/api/customer-feedback', { action: 'lookup', token }, fetcher, true);
  return {
    status: String(p.status ?? 'pending'),
    ready: p.ready === true,
    serviceType: String(p.serviceType ?? ''),
    preferredDate: String(p.preferredDate ?? ''),
    reviewSubmitted: p.reviewSubmitted === true,
    issueSubmitted: p.issueSubmitted === true,
    issueStatus: typeof p.issueStatus === 'string' ? p.issueStatus : null,
  };
}

export async function sendReview(token: string, rating: number, message: string, fetcher?: typeof fetch) {
  await post(
    '/api/customer-feedback',
    { action: 'review', token, rating, message: clean(message, true), consent: true },
    fetcher,
  );
}

export async function sendIssue(token: string, message: string, fetcher?: typeof fetch) {
  await post(
    '/api/customer-feedback',
    { action: 'issue', token, message: clean(message, true), consent: true },
    fetcher,
  );
}

/** Adds or removes this phone's notification token for one request. Safe to repeat. */
export async function pushRegister(token: string, pushToken: string, fetcher?: typeof fetch) {
  await post('/api/customer-feedback', { action: 'push_register', token, pushToken }, fetcher, true);
}

export async function pushUnregister(token: string, pushToken: string, fetcher?: typeof fetch) {
  await post('/api/customer-feedback', { action: 'push_unregister', token, pushToken }, fetcher, true);
}

/** Shared status answers for the app's screens, so moving between them doesn't re-check every request. */
export const statusCache = new LookupCache((token) => lookup(token));

/** True when the server no longer recognises this private link (for example it was removed). */
export function isGone(error: unknown): boolean {
  return error instanceof ApiError && error.status === 404;
}
