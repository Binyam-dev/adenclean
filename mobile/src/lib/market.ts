// Pure helpers for the marketplace screens: money, labels and form checks. No network here.

export const MARKET_ENABLED = process.env.EXPO_PUBLIC_MARKETPLACE === '1';

export type MarketService = 'regular' | 'deep' | 'move-in-move-out' | 'post-party';

export const MARKET_SERVICES: { id: MarketService; title: string }[] = [
  { id: 'regular', title: 'Regular cleaning' },
  { id: 'deep', title: 'Deep clean' },
  { id: 'move-in-move-out', title: 'Move-in / move-out' },
  { id: 'post-party', title: 'After a party' },
];

export function marketServiceTitle(id: string): string {
  return MARKET_SERVICES.find((s) => s.id === id)?.title ?? 'Cleaning';
}

/** "$123.45" from integer cents. */
export function formatCents(cents: number | null | undefined): string {
  if (typeof cents !== 'number' || !Number.isFinite(cents)) return '';
  const dollars = Math.floor(Math.abs(cents) / 100);
  const rest = String(Math.abs(cents) % 100).padStart(2, '0');
  return `${cents < 0 ? '-' : ''}$${dollars.toLocaleString('en-US')}.${rest}`;
}

/** Integer cents from what someone typed ("120", "$120.50", "120.5"), or null if it isn't money. */
export function parseDollars(text: string): number | null {
  const trimmed = text.trim().replace(/^\$/, '').replace(/,/g, '');
  if (!/^\d{1,5}(\.\d{1,2})?$/.test(trimmed)) return null;
  const [whole, fraction = ''] = trimmed.split('.');
  return Number(whole) * 100 + Number(fraction.padEnd(2, '0'));
}

export const PRICE_LIMITS = { min: 2_000, max: 200_000 };

// Must match the server's PLATFORM_FEE_BPS; the server's figure is the one that is charged.
export const PLATFORM_FEE_BPS = Number(process.env.EXPO_PUBLIC_PLATFORM_FEE_BPS ?? 1500);

/** What the cleaner receives for a price, after the platform fee (rounded half up, like the server). */
export function payoutAfterFee(priceCents: number, feeBps = PLATFORM_FEE_BPS): { fee: number; payout: number } {
  const fee = Math.floor((priceCents * feeBps + 5_000) / 10_000);
  return { fee, payout: priceCents - fee };
}

export function checkPrice(text: string): string | null {
  const cents = parseDollars(text);
  if (cents === null) return 'Enter a price in dollars, like 120 or 120.50.';
  if (cents < PRICE_LIMITS.min || cents > PRICE_LIMITS.max) {
    return `Enter a price from ${formatCents(PRICE_LIMITS.min)} to ${formatCents(PRICE_LIMITS.max)}.`;
  }
  return null;
}

export function checkZip(text: string): string | null {
  return /^\d{5}$/.test(text.trim()) ? null : 'Enter a 5-digit ZIP code.';
}

export function checkCode(text: string): string | null {
  return /^\d{6}$/.test(text.trim()) ? null : 'Enter the 6-digit code from the email.';
}

const JOB_LABELS: Record<string, string> = {
  open: 'Taking offers',
  booked: 'Booked',
  in_progress: 'In progress',
  awaiting_confirmation: 'Waiting for you to confirm',
  completed: 'Done',
  cancelled: 'Cancelled',
  expired: 'No offer accepted',
  disputed: 'Under review',
  draft: 'Draft',
};

export function jobStatusLabel(status: string): string {
  return JOB_LABELS[status] ?? status;
}

const OFFER_LABELS: Record<string, string> = {
  pending: 'Waiting for an answer',
  countered: 'Counter-offer',
  accepted: 'Accepted',
  declined: 'Declined',
  withdrawn: 'Withdrawn',
  expired: 'Closed',
};

export function offerStatusLabel(status: string): string {
  return OFFER_LABELS[status] ?? status;
}

/** True when this side of the offer should answer it now. */
export function myTurn(offer: { status: string; awaiting: string }, me: 'customer' | 'cleaner'): boolean {
  return (offer.status === 'pending' || offer.status === 'countered') && offer.awaiting === me;
}

/** "Mon, Dec 1 to Fri, Dec 5" from two ISO dates, read as local calendar days. */
export function dateRange(from: string, to: string): string {
  const fmt = (iso: string) => {
    const [y, m, d] = iso.split('-').map(Number);
    return new Date(y, m - 1, d).toLocaleDateString('en-US', { weekday: 'short', month: 'short', day: 'numeric' });
  };
  return from === to ? fmt(from) : `${fmt(from)} to ${fmt(to)}`;
}
