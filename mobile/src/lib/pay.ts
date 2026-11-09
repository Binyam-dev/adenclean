// Card payment through Stripe's PaymentSheet (iPhone and Android). The card number is typed
// into Stripe's own sheet, so it never passes through AdenClean's app code or server.
// Needs a development or store build: Expo Go does not include Stripe's native module.
//
// Stripe is loaded only when someone pays, never at startup. Version 1 store builds leave the
// native module out entirely (see react-native.config.js), and this file must not import it at
// the top: that would run Stripe's code on launch even though nothing uses it.

export type PayResult = { status: 'paid' | 'canceled' | 'unavailable' | 'failed'; message?: string };

export async function payWithSheet(clientSecret: string, publishableKey: string): Promise<PayResult> {
  if (!publishableKey) return { status: 'unavailable', message: 'Payments are not turned on yet.' };
  try {
    // eslint-disable-next-line @typescript-eslint/no-require-imports
    const { initPaymentSheet, initStripe, presentPaymentSheet } = require('@stripe/stripe-react-native') as typeof import('@stripe/stripe-react-native');
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
