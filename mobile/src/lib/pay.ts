// Card payment through Stripe's PaymentSheet (iPhone and Android). The card number is typed
// into Stripe's own sheet, so it never passes through AdenClean's app code or server.
// Needs a development or store build: Expo Go does not include Stripe's native module.

import { initPaymentSheet, initStripe, presentPaymentSheet } from '@stripe/stripe-react-native';

export type PayResult = { status: 'paid' | 'canceled' | 'unavailable' | 'failed'; message?: string };

export async function payWithSheet(clientSecret: string, publishableKey: string): Promise<PayResult> {
  if (!publishableKey) return { status: 'unavailable', message: 'Payments are not turned on yet.' };
  try {
    await initStripe({ publishableKey, urlScheme: 'adenclean' });
    const init = await initPaymentSheet({
      merchantDisplayName: 'AdenClean',
      paymentIntentClientSecret: clientSecret,
      returnURL: 'adenclean://stripe-redirect',
    });
    if (init.error) return { status: 'failed', message: init.error.message };
    const result = await presentPaymentSheet();
    if (!result.error) return { status: 'paid' };
    if (result.error.code === 'Canceled') return { status: 'canceled' };
    return { status: 'failed', message: result.error.message };
  } catch {
    return { status: 'unavailable', message: 'Card payments need the installed AdenClean app, not Expo Go.' };
  }
}
