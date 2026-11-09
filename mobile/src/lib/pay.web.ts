// The browser preview cannot take cards; payment happens in the iPhone and Android apps.

export type PayResult = { status: 'paid' | 'canceled' | 'unavailable' | 'failed'; message?: string };

export async function payWithSheet(_clientSecret: string, _publishableKey: string): Promise<PayResult> {
  return { status: 'unavailable', message: 'Pay in the AdenClean app on your phone.' };
}
