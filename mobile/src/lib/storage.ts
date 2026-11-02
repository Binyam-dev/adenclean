import * as SecureStore from 'expo-secure-store';
import { Platform } from 'react-native';

// Each request keeps its private link code on the phone so the person can come back to it.
// Native: the iOS Keychain / Android Keystore through expo-secure-store.
// Web: localStorage, used only for development and for taking store screenshots.

export type SavedRequest = {
  reference: string;
  token: string;
  createdAt: string; // ISO timestamp
  service: string;
  date: string; // YYYY-MM-DD
  time: string; // empty when the request was added from a link
  imported?: boolean;
};

const INDEX_KEY = 'adenclean.requests';
const itemKey = (reference: string) => `adenclean.request.${reference}`;
const MAX_SAVED = 60;

async function read(key: string): Promise<string | null> {
  if (Platform.OS === 'web') {
    try {
      return globalThis.localStorage?.getItem(key) ?? null;
    } catch {
      return null;
    }
  }
  try {
    return await SecureStore.getItemAsync(key);
  } catch {
    return null;
  }
}

async function write(key: string, value: string): Promise<void> {
  if (Platform.OS === 'web') {
    globalThis.localStorage?.setItem(key, value);
    return;
  }
  await SecureStore.setItemAsync(key, value);
}

async function remove(key: string): Promise<void> {
  if (Platform.OS === 'web') {
    globalThis.localStorage?.removeItem(key);
    return;
  }
  try {
    await SecureStore.deleteItemAsync(key);
  } catch {
    // Already gone.
  }
}

async function readIndex(): Promise<string[]> {
  const raw = await read(INDEX_KEY);
  if (!raw) return [];
  try {
    const parsed = JSON.parse(raw);
    return Array.isArray(parsed) ? parsed.filter((v): v is string => typeof v === 'string') : [];
  } catch {
    return [];
  }
}

export async function listSaved(): Promise<SavedRequest[]> {
  const refs = await readIndex();
  const items = await Promise.all(refs.map((ref) => getSaved(ref)));
  return items
    .filter((item): item is SavedRequest => item !== null)
    .sort((a, b) => b.createdAt.localeCompare(a.createdAt));
}

export async function getSaved(reference: string): Promise<SavedRequest | null> {
  const raw = await read(itemKey(reference));
  if (!raw) return null;
  try {
    const value = JSON.parse(raw) as SavedRequest;
    return typeof value.token === 'string' && typeof value.reference === 'string' ? value : null;
  } catch {
    return null;
  }
}

export async function saveRequest(item: SavedRequest): Promise<void> {
  const refs = (await readIndex()).filter((ref) => ref !== item.reference);
  refs.unshift(item.reference);
  const dropped = refs.splice(MAX_SAVED);
  await write(itemKey(item.reference), JSON.stringify(item));
  await write(INDEX_KEY, JSON.stringify(refs));
  await Promise.all(dropped.map((ref) => remove(itemKey(ref))));
}

export async function removeRequest(reference: string): Promise<void> {
  const refs = (await readIndex()).filter((ref) => ref !== reference);
  await write(INDEX_KEY, JSON.stringify(refs));
  await remove(itemKey(reference));
}

export async function clearAll(): Promise<void> {
  const refs = await readIndex();
  await Promise.all(refs.map((ref) => remove(itemKey(ref))));
  await remove(INDEX_KEY);
}
