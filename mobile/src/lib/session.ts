// The signed-in user's session token, kept in the Keychain / Keystore (localStorage on web,
// development only), plus a tiny store so screens update when someone signs in or out.

import * as SecureStore from 'expo-secure-store';
import { useEffect, useState } from 'react';
import { Platform } from 'react-native';

import { Client, type User } from './v1';

const TOKEN_KEY = 'adenclean.session';

type Session = { token: string | null; user: User | null; loaded: boolean };

let current: Session = { token: null, user: null, loaded: false };
const listeners = new Set<(s: Session) => void>();

function set(next: Session) {
  current = next;
  listeners.forEach((fn) => fn(current));
}

async function readToken(): Promise<string | null> {
  try {
    if (Platform.OS === 'web') return globalThis.localStorage?.getItem(TOKEN_KEY) ?? null;
    return await SecureStore.getItemAsync(TOKEN_KEY);
  } catch {
    return null;
  }
}

async function writeToken(token: string | null) {
  if (Platform.OS === 'web') {
    if (token) globalThis.localStorage?.setItem(TOKEN_KEY, token);
    else globalThis.localStorage?.removeItem(TOKEN_KEY);
    return;
  }
  if (token) await SecureStore.setItemAsync(TOKEN_KEY, token);
  else await SecureStore.deleteItemAsync(TOKEN_KEY).catch(() => undefined);
}

/** Load the saved token and check it with the server once at startup. */
export async function restore(): Promise<void> {
  if (current.loaded) return;
  const token = await readToken();
  if (!token) return set({ token: null, user: null, loaded: true });
  try {
    const user = await new Client(token).me();
    set({ token, user, loaded: true });
  } catch {
    // Expired or offline: keep the token only when we could not reach the server.
    set({ token, user: null, loaded: true });
  }
}

export async function signedIn(token: string, user: User) {
  await writeToken(token);
  set({ token, user, loaded: true });
}

export async function signOut() {
  await writeToken(null);
  set({ token: null, user: null, loaded: true });
}

export async function refreshUser() {
  if (!current.token) return;
  const user = await new Client(current.token).me();
  set({ ...current, user });
}

export function useSession(): Session & { client: Client } {
  const [state, setState] = useState(current);
  useEffect(() => {
    listeners.add(setState);
    void restore();
    return () => {
      listeners.delete(setState);
    };
  }, []);
  return { ...state, client: new Client(state.token) };
}
