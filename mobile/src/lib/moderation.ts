// Words and rules for reporting and blocking. Pure: no network here. The server enforces
// everything (who can report what, the hourly limit, the text filter); this only shapes the screens.

import { SUPPORT_EMAIL } from './config';

// Must match the server's REASONS. The server rejects anything else.
export const REPORT_REASONS: { id: string; label: string }[] = [
  { id: 'harassment', label: 'Harassment or abuse' },
  { id: 'unsafe', label: 'Unsafe or threatening' },
  { id: 'spam', label: 'Spam or an unwanted offer' },
  { id: 'off_platform', label: 'Asks to pay or talk outside AdenClean' },
  { id: 'fake', label: 'Fake or misleading' },
  { id: 'other', label: 'Something else' },
];

export const REPORT_DETAIL_MAX = 500;

export function reportThanks(merged: boolean): string {
  const head = merged ? 'You already reported this. We have it.' : 'Thanks. We review every report within 24 hours.';
  return `${head} Questions: ${SUPPORT_EMAIL}.`;
}

/** What the person is told before blocking, so they know what it does and does not do. */
export const BLOCK_EXPLANATION =
  "You and this person will no longer see each other's jobs or offers, and their open offers are withdrawn. " +
  'They are not told. A booking you already have together carries on until it is finished.';

export function canSubmitReport(reason: string | null, detail: string): boolean {
  return !!reason && REPORT_REASONS.some((r) => r.id === reason) && detail.length <= REPORT_DETAIL_MAX;
}

/** "Hana (blocked Nov 9)" style line for the blocked list. */
export function blockedLine(name: string, createdAt: string): string {
  const date = new Date(createdAt);
  if (Number.isNaN(date.getTime())) return name;
  return `${name}, blocked ${date.toLocaleDateString('en-US', { month: 'short', day: 'numeric' })}`;
}
