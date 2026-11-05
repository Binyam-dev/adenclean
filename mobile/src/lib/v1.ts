// Client for the marketplace API (/api/v1). Every call that needs an account sends the
// session token as a Bearer header. Errors come back as ApiError with a readable message.

import { ApiError } from './api';
import { API_URL } from './config';

const NETWORK_MESSAGE = "Can't reach AdenClean. Check your connection and try again.";
const SERVER_MESSAGE = 'Something went wrong on our side. Try again in a moment.';

type Json = Record<string, unknown>;

export type User = { id: string; email: string; displayName: string; roles: string[] };

export type Job = {
  id: string;
  status: string;
  service_type: string;
  zip: string;
  bedrooms: number;
  bathrooms: number;
  supplies: 'customer' | 'cleaner';
  date_from: string;
  date_to: string;
  budget_cents: number | null;
  notes: string | null;
  created_at: string;
  expires_at: string;
  booked_offer_id?: string | null;
  price_cents?: number | null;
};

export type Offer = {
  id: string;
  job_id: string;
  price_cents: number;
  status: string;
  counter_rounds: number;
  awaiting: 'customer' | 'cleaner';
  message: string | null;
  created_at: string;
  expires_at: string;
  cleaner_name?: string;
};

export type NewJob = {
  serviceType: string;
  zip: string;
  bedrooms: number;
  bathrooms: number;
  supplies: 'customer' | 'cleaner';
  dateFrom: string;
  dateTo: string;
  budgetCents?: number;
  notes?: string;
};

export type Vetting = {
  status: 'applied' | 'in_review' | 'approved' | 'pre_adverse' | 'denied' | 'withdrawn';
  identity_status: 'not_started' | 'pending' | 'verified' | 'failed';
  background_status: 'not_started' | 'invited' | 'clear' | 'consider' | 'suspended';
  consent_at: string | null;
  dispute_deadline: string | null;
  dispute_open: number;
};

export type Booking = {
  job_id: string;
  price_cents: number;
  tip_cents: number;
  payment_status: 'unpaid' | 'paid' | 'refunded';
  payout_status: 'none' | 'sent';
  starts_on: string;
  checked_in_at: string | null;
  checked_out_at: string | null;
  confirmed_at: string | null;
  cancelled_by: 'customer' | 'cleaner' | null;
  total_cents?: number;
  fee_cents?: number;
  payout_cents?: number;
};

/** Where a cleaner's Stripe payout setup stands. "off" means payments are not turned on. */
export type PayoutState = 'off' | 'none' | 'incomplete' | 'ready';

export type PaymentStart = { clientSecret: string; publishableKey: string };

export class Client {
  constructor(
    private token: string | null,
    // Wrapped so fetch is never called as a method of this object: browsers throw
    // "Illegal invocation" when window.fetch runs with a different `this`.
    private fetcher: typeof fetch = (input, init) => fetch(input, init),
  ) {}

  private async call(method: 'GET' | 'POST', path: string, body?: Json): Promise<Json> {
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), 15000);
    const headers: Record<string, string> = {};
    if (body) headers['Content-Type'] = 'application/json';
    if (this.token) headers.Authorization = `Bearer ${this.token}`;
    let response: Response;
    try {
      response = await this.fetcher(`${API_URL}${path}`, {
        method,
        headers,
        body: body ? JSON.stringify(body) : undefined,
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
      // Not JSON; the status check below decides.
    }
    if (!response.ok || payload.ok === false) {
      const message = typeof payload.error === 'string' ? payload.error : '';
      if (response.status >= 500 && response.status !== 503) throw new ApiError('server', response.status, SERVER_MESSAGE);
      throw new ApiError('client', response.status, message || SERVER_MESSAGE);
    }
    return payload;
  }

  requestCode(email: string) {
    return this.call('POST', '/api/v1/auth/request-code', { email: email.trim().toLowerCase() });
  }

  async verifyCode(email: string, code: string, displayName: string, acceptTerms: boolean) {
    const p = await this.call('POST', '/api/v1/auth/verify-code', {
      email: email.trim().toLowerCase(),
      code: code.trim(),
      displayName: displayName.trim(),
      acceptTerms,
    });
    return { token: String(p.token), user: p.user as User };
  }

  async me(): Promise<User> {
    return (await this.call('GET', '/api/v1/me')).user as User;
  }

  async deleteAccount(): Promise<void> {
    await this.call('POST', '/api/v1/auth/delete-account', { confirm: 'DELETE' });
  }

  async createJob(job: NewJob): Promise<Job> {
    return (await this.call('POST', '/api/v1/jobs', job as unknown as Json)).job as Job;
  }

  async myJobs(): Promise<Job[]> {
    return (await this.call('GET', '/api/v1/jobs/mine')).jobs as Job[];
  }

  async openJobs(): Promise<Job[]> {
    return (await this.call('GET', '/api/v1/jobs/open')).jobs as Job[];
  }

  async job(id: string): Promise<{ job: Job; role: 'customer' | 'cleaner'; myOffer: Offer | null }> {
    const p = await this.call('GET', `/api/v1/jobs/${id}`);
    return { job: p.job as Job, role: p.role as 'customer' | 'cleaner', myOffer: (p.myOffer as Offer) ?? null };
  }

  async cancelJob(id: string): Promise<void> {
    await this.call('POST', `/api/v1/jobs/${id}/cancel`, {});
  }

  async offers(jobId: string): Promise<Offer[]> {
    return (await this.call('GET', `/api/v1/jobs/${jobId}/offers`)).offers as Offer[];
  }

  async sendOffer(jobId: string, priceCents: number, message: string): Promise<Offer> {
    const p = await this.call('POST', `/api/v1/jobs/${jobId}/offers`, { priceCents, message: message.trim() });
    return p.offer as Offer;
  }

  async counter(offerId: string, priceCents: number): Promise<void> {
    await this.call('POST', `/api/v1/offers/${offerId}/counter`, { priceCents });
  }

  async answer(offerId: string, action: 'accept' | 'decline' | 'withdraw'): Promise<void> {
    await this.call('POST', `/api/v1/offers/${offerId}/${action}`, {});
  }

  // -- cleaner vetting -------------------------------------------------------------

  /** The signed-in person's cleaner application, or null if they have not applied. */
  async vetting(): Promise<Vetting | null> {
    try {
      return (await this.call('GET', '/api/v1/cleaner/status')).vetting as Vetting;
    } catch (e) {
      if (e instanceof ApiError && e.status === 404) return null;
      throw e;
    }
  }

  async applyToClean(): Promise<Vetting> {
    return (await this.call('POST', '/api/v1/cleaner/apply', { over18: true })).vetting as Vetting;
  }

  async disclosure(): Promise<{ version: string; text: string }> {
    const p = await this.call('GET', '/api/v1/cleaner/disclosure');
    return { version: String(p.version), text: String(p.text) };
  }

  async authorizeBackgroundCheck(fullName: string): Promise<Vetting> {
    const p = await this.call('POST', '/api/v1/cleaner/authorize', { authorize: true, fullName: fullName.trim() });
    return p.vetting as Vetting;
  }

  /** A Stripe Identity page to open in the browser. */
  async identityLink(): Promise<string> {
    return String((await this.call('POST', '/api/v1/cleaner/identity', {})).url);
  }

  /** A Checkr form to open in the browser. The cleaner enters their SSN there, never in this app. */
  async backgroundLink(): Promise<string> {
    return String((await this.call('POST', '/api/v1/cleaner/background', {})).url);
  }

  async disputeDecision(): Promise<Vetting> {
    return (await this.call('POST', '/api/v1/cleaner/dispute', {})).vetting as Vetting;
  }

  // -- payouts and bookings ----------------------------------------------------------

  async payoutState(): Promise<PayoutState> {
    try {
      const p = await this.call('POST', '/api/v1/payouts/refresh', {});
      return p.payoutsEnabled ? 'ready' : 'incomplete';
    } catch (e) {
      if (e instanceof ApiError && e.status === 404) return 'none';
      if (e instanceof ApiError && e.status === 503) return 'off';
      throw e;
    }
  }

  /** A Stripe page where the cleaner adds their bank details. */
  async payoutLink(): Promise<string> {
    return String((await this.call('POST', '/api/v1/payouts/onboard', {})).url);
  }

  async booking(jobId: string): Promise<Booking> {
    return (await this.call('GET', `/api/v1/jobs/${jobId}/booking`)).booking as Booking;
  }

  async startPayment(jobId: string): Promise<PaymentStart> {
    const p = await this.call('POST', `/api/v1/jobs/${jobId}/pay`, {});
    return { clientSecret: String(p.clientSecret), publishableKey: String(p.publishableKey ?? '') };
  }

  async startTip(jobId: string, tipCents: number): Promise<PaymentStart> {
    const p = await this.call('POST', `/api/v1/jobs/${jobId}/tip`, { tipCents });
    return { clientSecret: String(p.clientSecret), publishableKey: String(p.publishableKey ?? '') };
  }

  async bookingStep(jobId: string, step: 'check-in' | 'check-out' | 'confirm'): Promise<void> {
    await this.call('POST', `/api/v1/jobs/${jobId}/${step}`, {});
  }

  async cancelBooking(jobId: string): Promise<{ refundCents: number; cleanerFeeCents: number }> {
    const p = await this.call('POST', `/api/v1/jobs/${jobId}/cancel-booking`, {});
    return { refundCents: Number(p.refundCents ?? 0), cleanerFeeCents: Number(p.cleanerFeeCents ?? 0) };
  }
}

/** The session is no longer valid (signed out elsewhere, deleted, or expired). */
export function isSignedOut(error: unknown): boolean {
  return error instanceof ApiError && error.status === 401;
}
