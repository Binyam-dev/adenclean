import type { Lookup } from './api';

export type Tone = 'wait' | 'good' | 'done' | 'stop';

export type StatusCopy = { label: string; detail: string; tone: Tone };

// Plain language for each state. The server's approval means "ready for follow-up", not a
// booking, so the copy never says "confirmed" or "booked".
export function statusCopy(status: string): StatusCopy {
  switch (status) {
    case 'pending':
      return { label: 'Received', detail: 'AdenClean has your request and will review it.', tone: 'wait' };
    case 'approved':
      return {
        label: 'Approved for follow-up',
        detail: "This isn't a confirmed booking yet. AdenClean will follow up to talk through the details.",
        tone: 'good',
      };
    case 'completed':
      return {
        label: 'Completed',
        detail: 'Your service is marked complete. You can leave a review or report a problem below.',
        tone: 'done',
      };
    case 'declined':
      return {
        label: 'Not available',
        detail: "AdenClean can't take this request. You're welcome to send a new one with different details.",
        tone: 'stop',
      };
    case 'cancelled':
      return { label: 'Cancelled', detail: 'This request was cancelled.', tone: 'stop' };
    default:
      return { label: 'In review', detail: 'AdenClean is reviewing this request.', tone: 'wait' };
  }
}

export function issueCopy(status: string | null): string {
  switch (status) {
    case 'in_review':
      return 'AdenClean is looking into your report.';
    case 'resolved':
      return 'AdenClean marked your report as resolved.';
    case 'open':
    default:
      return 'AdenClean has your report and will review it.';
  }
}

export function feedbackAvailable(info: Lookup): boolean {
  return info.ready;
}
