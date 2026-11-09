import { router } from 'expo-router';
import * as WebBrowser from 'expo-web-browser';
import { useState } from 'react';

import { Notice } from '@/components/Bits';
import { Button } from '@/components/Button';
import { Checkbox, Header } from '@/components/Controls';
import { Field } from '@/components/Field';
import { Screen } from '@/components/Screen';
import { Text } from '@/components/Text';
import { ApiError } from '@/lib/api';
import { PRIVACY_URL, TERMS_URL } from '@/lib/config';
import { checkCode } from '@/lib/market';
import { signedIn } from '@/lib/session';
import { checkEmail } from '@/lib/validation';
import { Client } from '@/lib/v1';

export default function SignIn() {
  const [step, setStep] = useState<'email' | 'code'>('email');
  const [email, setEmail] = useState('');
  const [code, setCode] = useState('');
  const [name, setName] = useState('');
  const [accepted, setAccepted] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const client = new Client(null);

  const sendCode = async () => {
    const problem = checkEmail(email);
    if (problem) return setError(problem);
    setBusy(true);
    setError(null);
    try {
      await client.requestCode(email);
      setStep('code');
    } catch (e) {
      setError(e instanceof ApiError ? e.message : 'Something went wrong. Try again.');
    } finally {
      setBusy(false);
    }
  };

  const verify = async () => {
    const problem = checkCode(code);
    if (problem) return setError(problem);
    if (!accepted) return setError('Accept the terms and privacy policy to continue.');
    setBusy(true);
    setError(null);
    try {
      const { token, user } = await client.verifyCode(email, code, name, true);
      await signedIn(token, user);
      if (router.canGoBack()) router.back();
      else router.replace('/');
    } catch (e) {
      setError(e instanceof ApiError ? e.message : 'Something went wrong. Try again.');
    } finally {
      setBusy(false);
    }
  };

  return (
    <Screen>
      <Header title={step === 'email' ? 'Sign in or create an account' : 'Check your email'}
        onBack={step === 'code' ? () => { setStep('email'); setCode(''); setError(null); } : undefined} />
      {step === 'email' ? (
        <>
          <Text tone="soft">We email you a 6-digit code. No password to remember.</Text>
          <Field label="Email" value={email} onChangeText={setEmail} keyboardType="email-address" autoCapitalize="none"
            autoComplete="email" textContentType="emailAddress" returnKeyType="send" onSubmitEditing={() => void sendCode()}
            testID="signin-email" />
          {error ? <Notice kind="error">{error}</Notice> : null}
          <Button label="Send code" onPress={() => void sendCode()} loading={busy} testID="signin-send" />
        </>
      ) : (
        <>
          <Text tone="soft">If {email.trim()} can sign in, a code is on its way. It expires in 10 minutes.</Text>
          <Field label="6-digit code" value={code} onChangeText={setCode} keyboardType="number-pad" maxLength={6}
            autoComplete="one-time-code" textContentType="oneTimeCode" testID="signin-code" />
          <Field label="Your first name" optional hint="Shown to the people you book with." value={name}
            onChangeText={setName} autoComplete="given-name" textContentType="givenName" maxLength={80} />
          <Checkbox checked={accepted} onChange={setAccepted}>
            <Text>
              I agree to the{' '}
              <Text tone="primary" style={{ textDecorationLine: 'underline' }} accessibilityRole="link"
                onPress={() => void WebBrowser.openBrowserAsync(TERMS_URL)}>terms</Text>
              {' '}and{' '}
              <Text tone="primary" style={{ textDecorationLine: 'underline' }} accessibilityRole="link"
                onPress={() => void WebBrowser.openBrowserAsync(PRIVACY_URL)}>privacy policy</Text>
              . You must be 18 or older. No abusive, harassing or unsafe content: we may remove content and accounts.
              You can report or block anyone in the app.
            </Text>
          </Checkbox>
          {error ? <Notice kind="error">{error}</Notice> : null}
          <Button label="Sign in" onPress={() => void verify()} loading={busy} testID="signin-verify" />
          <Button variant="quiet" label="Use a different email" onPress={() => { setStep('email'); setCode(''); setError(null); }} />
        </>
      )}
    </Screen>
  );
}
