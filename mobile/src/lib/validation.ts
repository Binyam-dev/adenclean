// Mirrors the server's rules (main.py) so people hear about a problem before they send.
// Pure functions with no React Native imports, so they can be unit-tested with Node.

export type ServiceId = 'routine' | 'deep' | 'move-in/move-out';
export type TimeId = 'morning' | 'afternoon' | 'flexible';

export const SERVICES: { id: ServiceId; title: string; tagline: string; description: string }[] = [
  {
    id: 'routine',
    title: 'Routine home cleaning',
    tagline: 'For the everyday reset',
    description: 'Help with the familiar tasks that keep a home feeling comfortable.',
  },
  {
    id: 'deep',
    title: 'Deep cleaning',
    tagline: 'For a considered refresh',
    description: 'A more detailed clean for the areas that may need extra attention.',
  },
  {
    id: 'move-in/move-out',
    title: 'Move-in / move-out',
    tagline: 'For a change of chapter',
    description: 'Cleaning support for the transition between homes.',
  },
];

export const TIMES: { id: TimeId; title: string }[] = [
  { id: 'morning', title: 'Morning' },
  { id: 'afternoon', title: 'Afternoon' },
  { id: 'flexible', title: 'Flexible' },
];

export const LIMITS = { name: 100, email: 254, area: 100, notes: 800, feedback: 1200, feedbackMin: 10 } as const;

export type RequestDraft = {
  service: ServiceId | null;
  date: string | null; // YYYY-MM-DD
  time: TimeId | null;
  name: string;
  email: string;
  area: string;
  notes: string;
  consent: boolean;
};

export const emptyDraft: RequestDraft = {
  service: null,
  date: null,
  time: null,
  name: '',
  email: '',
  area: '',
  notes: '',
  consent: false,
};

/** Collapse whitespace the way the server does, so what we validate is what it will see. */
export function clean(value: string, allowNewlines = false): string {
  let text = value.replace(/\r\n?/g, '\n');
  if (allowNewlines) {
    text = text.replace(/[^\S\n]+/g, ' ').replace(/\n{3,}/g, '\n\n');
  } else {
    text = text.split(/\s+/).filter(Boolean).join(' ');
  }
  return text.trim();
}

const EMAIL = /^[^@\s]+@[^@\s]+\.[^@\s]{2,}$/;
// eslint-disable-next-line no-control-regex
const CONTROL = /[\u0000-\u0008\u000B-\u001F]/;

export function checkName(value: string): string | null {
  const text = clean(value);
  if (!text) return 'Enter your name.';
  if (text.length > LIMITS.name) return `Use ${LIMITS.name} characters or fewer.`;
  if (CONTROL.test(text)) return 'Remove special characters.';
  return null;
}

export function checkEmail(value: string): string | null {
  const text = clean(value).toLowerCase();
  if (!text) return 'Enter your email address.';
  if (text.length > LIMITS.email || !EMAIL.test(text)) return 'Enter an email like name@example.com.';
  return null;
}

export function checkArea(value: string): string | null {
  const text = clean(value);
  if (!text) return 'Enter your town or ZIP code.';
  if (text.length > LIMITS.area) return `Use ${LIMITS.area} characters or fewer.`;
  if (CONTROL.test(text)) return 'Remove special characters.';
  return null;
}

export function checkNotes(value: string): string | null {
  const text = clean(value, true);
  if (text.length > LIMITS.notes) return `Use ${LIMITS.notes} characters or fewer.`;
  if (CONTROL.test(text)) return 'Remove special characters.';
  return null;
}

export function checkFeedback(value: string): string | null {
  const text = clean(value, true);
  if (text.length < LIMITS.feedbackMin) return `Write at least ${LIMITS.feedbackMin} characters.`;
  if (text.length > LIMITS.feedback) return `Use ${LIMITS.feedback} characters or fewer.`;
  if (CONTROL.test(text)) return 'Remove special characters.';
  return null;
}

export type StepId = 'service' | 'when' | 'details' | 'review';
export const STEPS: StepId[] = ['service', 'when', 'details', 'review'];

/** Which of the four steps is complete. Drives the lit windows on the house. */
export function stepsComplete(draft: RequestDraft): Record<StepId, boolean> {
  return {
    service: draft.service !== null,
    when: draft.date !== null && draft.time !== null,
    details: !checkName(draft.name) && !checkEmail(draft.email) && !checkArea(draft.area) && !checkNotes(draft.notes),
    review: draft.consent,
  };
}

export function isReady(draft: RequestDraft): boolean {
  return Object.values(stepsComplete(draft)).every(Boolean);
}

export type DetailErrors = { name?: string; email?: string; area?: string; notes?: string };

export function detailErrors(draft: RequestDraft): DetailErrors {
  const errors: DetailErrors = {};
  const name = checkName(draft.name);
  const email = checkEmail(draft.email);
  const area = checkArea(draft.area);
  const notes = checkNotes(draft.notes);
  if (name) errors.name = name;
  if (email) errors.email = email;
  if (area) errors.area = area;
  if (notes) errors.notes = notes;
  return errors;
}

export type DateOption = { iso: string; weekday: string; day: string; month: string; spoken: string };

const WEEKDAYS = ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat'];
const MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
const WEEKDAYS_LONG = ['Sunday', 'Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday'];
const MONTHS_LONG = [
  'January', 'February', 'March', 'April', 'May', 'June',
  'July', 'August', 'September', 'October', 'November', 'December',
];

function pad(n: number): string {
  return String(n).padStart(2, '0');
}

/**
 * The next `count` days, starting tomorrow. Starting tomorrow (not today) keeps a request
 * valid no matter how the server's clock and the phone's time zone differ.
 */
export function dateOptions(from: Date, count = 21): DateOption[] {
  const options: DateOption[] = [];
  for (let offset = 1; offset <= count; offset += 1) {
    const d = new Date(from.getFullYear(), from.getMonth(), from.getDate() + offset);
    options.push({
      iso: `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`,
      weekday: WEEKDAYS[d.getDay()],
      day: String(d.getDate()),
      month: MONTHS[d.getMonth()],
      spoken: `${WEEKDAYS_LONG[d.getDay()]}, ${MONTHS_LONG[d.getMonth()]} ${d.getDate()}`,
    });
  }
  return options;
}

/** "2026-12-03" -> "Thursday, December 3". Falls back to the input if it is not a date. */
export function speakDate(iso: string): string {
  const match = /^(\d{4})-(\d{2})-(\d{2})$/.exec(iso);
  if (!match) return iso;
  const d = new Date(Number(match[1]), Number(match[2]) - 1, Number(match[3]));
  if (Number.isNaN(d.getTime())) return iso;
  return `${WEEKDAYS_LONG[d.getDay()]}, ${MONTHS_LONG[d.getMonth()]} ${d.getDate()}`;
}

export function serviceTitle(id: string): string {
  const match = SERVICES.find((s) => s.id === id || (id.startsWith('move-in') && s.id === 'move-in/move-out'));
  return match ? match.title : 'Cleaning';
}

export function timeTitle(id: string): string {
  return TIMES.find((t) => t.id === id)?.title ?? id;
}

const TOKEN = /[A-Za-z0-9_-]{43}/;

/**
 * Finds a private feedback code in whatever the person pasted: the full link from the
 * website (…/feedback.html#token=CODE), "token=CODE", or just the code.
 */
export function extractToken(text: string): string | null {
  const trimmed = text.trim();
  const param = /token=([A-Za-z0-9_-]{43})(?![A-Za-z0-9_-])/.exec(trimmed);
  if (param) return param[1];
  const bare = new RegExp(`^${TOKEN.source}$`).exec(trimmed);
  return bare ? bare[0] : null;
}
