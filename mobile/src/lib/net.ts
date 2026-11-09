// Network behaviour shared by the customer API: patience for a sleeping server, safe retries,
// and a "this is slow" signal the screens can show.
//
// The server runs on a host that can put it to sleep when idle. The first request after a quiet
// spell is held until it wakes, which can take most of a minute. So:
//
// - Reading (checking a request's status) is safe to repeat: it retries network failures and
//   502/503/504 up to three times, waiting a little longer each time.
// - Sending a request is NOT safe to repeat after the connection drops, because the server may
//   already have saved it (a second record, a second private code). It waits longer for one
//   answer and only retries a 502 or 503, which mean the server never saw the request.

export const retry = {
  delaysMs: [1500, 4000],
  readTimeoutMs: 30_000,
  writeTimeoutMs: 60_000,
  slowAfterMs: 4_000,
  sleep: (ms: number) => new Promise<void>((resolve) => setTimeout(resolve, ms)),
};

/** Whether to try again after this outcome. `status` is 0 for a network failure. */
export function shouldRetry(status: number, idempotent: boolean, attempt: number): boolean {
  if (attempt >= retry.delaysMs.length) return false;
  if (status === 0) return idempotent;
  if (status === 502 || status === 503) return true;
  return idempotent && status === 504;
}

// -- "waking up" signal ----------------------------------------------------------------

type Listener = () => void;
let slowRequests = 0;
const listeners = new Set<Listener>();

function emit() {
  listeners.forEach((listener) => listener());
}

/** For useSyncExternalStore: true while any request has been waiting longer than slowAfterMs. */
export function subscribeSlow(listener: Listener): () => void {
  listeners.add(listener);
  return () => {
    listeners.delete(listener);
  };
}

export function isSlow(): boolean {
  return slowRequests > 0;
}

/** Call when a request starts; call the returned function when it ends. */
export function trackSlow(): () => void {
  let marked = false;
  const timer = setTimeout(() => {
    marked = true;
    slowRequests += 1;
    emit();
  }, retry.slowAfterMs);
  return () => {
    clearTimeout(timer);
    if (marked) {
      marked = false;
      slowRequests -= 1;
      emit();
    }
  };
}
