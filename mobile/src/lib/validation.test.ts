import assert from 'node:assert/strict';
import { describe, it } from 'node:test';

import {
  LIMITS,
  checkArea,
  checkEmail,
  checkFeedback,
  checkName,
  checkNotes,
  clean,
  dateOptions,
  detailErrors,
  emptyDraft,
  extractToken,
  isReady,
  serviceTitle,
  speakDate,
  stepsComplete,
  type RequestDraft,
} from './validation';

const good: RequestDraft = {
  service: 'routine',
  date: '2026-12-03',
  time: 'morning',
  name: 'Pat Customer',
  email: 'Pat@Example.com',
  area: 'Silver Spring',
  notes: '',
  consent: true,
};

describe('validation matches the server', () => {
  it('collapses whitespace like the server does', () => {
    assert.equal(clean('  Pat   \t Customer  '), 'Pat Customer');
    assert.equal(clean('a\r\n\r\n\r\n\r\nb', true), 'a\n\nb');
  });

  it('accepts a complete request and rejects an empty one', () => {
    assert.equal(isReady(good), true);
    assert.equal(isReady(emptyDraft), false);
  });

  it('names, emails and areas', () => {
    assert.match(checkName('   ') ?? '', /Enter your name/);
    assert.equal(checkName('x'.repeat(LIMITS.name)), null);
    assert.ok(checkName('x'.repeat(LIMITS.name + 1)));
    assert.equal(checkEmail('pat@example.com'), null);
    for (const bad of ['', 'pat', 'pat@', 'pat@example', 'pat@exa mple.com', 'pat@example.c']) {
      assert.ok(checkEmail(bad), `should reject ${JSON.stringify(bad)}`);
    }
    assert.ok(checkArea(''));
    assert.equal(checkArea('20910'), null);
  });

  it('notes are optional but capped, and control characters are refused', () => {
    assert.equal(checkNotes(''), null);
    assert.ok(checkNotes('x'.repeat(LIMITS.notes + 1)));
    assert.ok(checkNotes('bad\u0007bell'));
    assert.equal(checkNotes('two\nlines are fine'), null);
  });

  it('feedback needs at least ten characters', () => {
    assert.ok(checkFeedback('too short'));
    assert.equal(checkFeedback('Spotless kitchen'), null);
    assert.ok(checkFeedback('x'.repeat(LIMITS.feedback + 1)));
  });

  it('reports each step as complete or not, which lights the windows', () => {
    assert.deepEqual(stepsComplete(emptyDraft), { service: false, when: false, details: false, review: false });
    assert.deepEqual(stepsComplete(good), { service: true, when: true, details: true, review: true });
    assert.equal(stepsComplete({ ...good, time: null }).when, false);
    assert.equal(stepsComplete({ ...good, consent: false }).review, false);
    assert.equal(stepsComplete({ ...good, email: 'nope' }).details, false);
  });

  it('lists only the fields that have a problem', () => {
    assert.deepEqual(detailErrors(good), {});
    assert.deepEqual(Object.keys(detailErrors({ ...good, name: '', area: '' })).sort(), ['area', 'name']);
  });
});

describe('dates', () => {
  it('start tomorrow, so a request is valid whatever the server clock says', () => {
    const options = dateOptions(new Date(2026, 10, 30, 23, 59), 3); // 30 Nov 2026, late evening
    assert.deepEqual(options.map((o) => o.iso), ['2026-12-01', '2026-12-02', '2026-12-03']);
    assert.equal(options[0].weekday, 'Tue');
    assert.equal(options[0].month, 'Dec');
  });

  it('crosses year ends and leap days', () => {
    assert.equal(dateOptions(new Date(2026, 11, 31), 1)[0].iso, '2027-01-01');
    assert.equal(dateOptions(new Date(2028, 1, 28), 1)[0].iso, '2028-02-29');
  });

  it('speaks a date in words', () => {
    assert.equal(speakDate('2026-12-03'), 'Thursday, December 3');
    assert.equal(speakDate('not a date'), 'not a date');
  });

  it('names services, including the server alias', () => {
    assert.equal(serviceTitle('deep'), 'Deep cleaning');
    assert.equal(serviceTitle('move-in/move-out'), 'Move-in / move-out');
    assert.equal(serviceTitle('move-in-out'), 'Move-in / move-out');
    assert.equal(serviceTitle('unknown'), 'Cleaning');
  });
});

describe('private links', () => {
  const code = 'a1B2c3D4e5F6g7H8i9J0k1L2m3N4o5P6q7R8s9T0uVw';
  it('finds the code in a pasted website link, a token parameter, or the bare code', () => {
    assert.equal(code.length, 43);
    assert.equal(extractToken(`https://adenclean.example.com/feedback.html#token=${code}`), code);
    assert.equal(extractToken(`  token=${code}  `), code);
    assert.equal(extractToken(code), code);
  });
  it('rejects anything else', () => {
    assert.equal(extractToken(''), null);
    assert.equal(extractToken('hello'), null);
    assert.equal(extractToken(`${code}x`), null);
    assert.equal(extractToken(`https://example.com/${code}`), null);
    assert.equal(extractToken(`token=${code}${code}`), null);
  });
});
