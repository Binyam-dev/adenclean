import { API_URL } from './config';
import { LookupCache } from './lookup-cache';
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

async function post(path: string, body: Json, fetcher: typeof fetch = fetch): Promise<Json> {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), 15000);
  let response: Response;
  try {
    response = await fetcher(`${API_URL}${path}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
      signal: controller.signal,
    });
  } catch {
    throw new ApiError('network', 0, NETWORK_MESSAGE);
  } finally {
    clearTimeout(timer);
  }

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
  const p = await post('/api/customer-feedback', { action: 'lookup', token }, fetcher);
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

/** Shared status answers for the app's screens, so moving between them doesn't re-check every request. */
export const statusCache = new LookupCache((token) => lookup(token));

/** True when the server no longer recognises this private link (for example it was removed). */
export function isGone(error: unknown): boolean {
  return error instanceof ApiError && error.status === 404;
}
