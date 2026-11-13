import Constants from 'expo-constants';
import * as Device from 'expo-device';
import * as Notifications from 'expo-notifications';
import { router } from 'expo-router';
import { useCallback, useEffect, useState } from 'react';
import { Platform } from 'react-native';

import { pushRegister, pushUnregister } from './api';
import * as core from './push-core';
import { flags, listSaved } from './storage';

const CHANNEL = 'request-updates';
const REFERENCE = /^[A-Za-z0-9]{6,20}$/;

function permissionOf(status: Notifications.NotificationPermissionsStatus): core.Permission {
  if (status.granted) return 'granted';
  // Only a refusal the system will not let us repeat counts as denied.
  return status.status === 'denied' && !status.canAskAgain ? 'denied' : 'undetermined';
}

async function ensureChannel(): Promise<void> {
  if (Platform.OS !== 'android') return;
  await Notifications.setNotificationChannelAsync(CHANNEL, {
    name: 'Request updates',
    importance: 3, // Android "default" importance: sound, no pop-up
  });
}

export const deps: core.PushDeps = {
  supported: Platform.OS !== 'web' && Device.isDevice,
  getPermission: async () => permissionOf(await Notifications.getPermissionsAsync()),
  askPermission: async () => {
    await ensureChannel(); // Android 13+ shows the prompt only after a channel exists
    return permissionOf(await Notifications.requestPermissionsAsync());
  },
  getPushToken: async () => {
    try {
      await ensureChannel();
      const projectId = Constants.expoConfig?.extra?.eas?.projectId ?? Constants.easConfig?.projectId;
      return (await Notifications.getExpoPushTokenAsync(projectId ? { projectId } : undefined)).data;
    } catch {
      return null;
    }
  },
  flags,
  register: pushRegister,
  unregister: pushUnregister,
  saved: async () => (await listSaved()).map(({ reference, token }) => ({ reference, token })),
};

/** Call once from the root layout: show alerts while the app is open, finish old removals,
 *  and open the right request when a notification is tapped. */
export function usePushSetup(): void {
  useEffect(() => {
    if (Platform.OS === 'web') return;
    Notifications.setNotificationHandler({
      handleNotification: async () => ({ shouldShowBanner: true, shouldShowList: true, shouldPlaySound: false, shouldSetBadge: false }),
    });
    void core.retryPending(deps);

    const open = (response: Notifications.NotificationResponse | null) => {
      const ref = response?.notification.request.content.data?.ref;
      if (typeof ref !== 'string' || !REFERENCE.test(ref)) return;
      setTimeout(() => router.push({ pathname: '/request/[ref]', params: { ref } }), 0);
    };
    open(Notifications.getLastNotificationResponse());
    const subscription = Notifications.addNotificationResponseReceivedListener(open);
    return () => subscription.remove();
  }, []);
}

export type PushView = { state: core.PushState | 'loading'; offer: boolean; busy: boolean; notice: string | null };

/** State and actions for the notification card and the switch under More. */
export function usePush() {
  const [view, setView] = useState<PushView>({ state: 'loading', offer: false, busy: false, notice: null });

  const refresh = useCallback(async (notice: string | null = null) => {
    const [state, offer] = await Promise.all([core.getState(deps), core.shouldOffer(deps)]);
    setView({ state, offer, busy: false, notice });
  }, []);

  useEffect(() => {
    let live = true;
    void Promise.all([core.getState(deps), core.shouldOffer(deps)]).then(([state, offer]) => {
      if (live) setView({ state, offer, busy: false, notice: null });
    });
    return () => {
      live = false;
    };
  }, []);

  const turnOn = useCallback(async () => {
    setView((v) => ({ ...v, busy: true, notice: null }));
    const result = await core.enable(deps);
    await refresh(
      result === 'blocked'
        ? 'Notifications are blocked for AdenClean. You can allow them in your phone settings.'
        : result === 'failed'
          ? "Couldn't turn on notifications. Try again in a moment."
          : null,
    );
  }, [refresh]);

  const turnOff = useCallback(async () => {
    setView((v) => ({ ...v, busy: true, notice: null }));
    const { pending } = await core.disable(deps);
    await refresh(pending > 0 ? "Notifications are off. Some requests couldn't be updated yet; we'll finish when you reopen the app." : null);
  }, [refresh]);

  const notNow = useCallback(async () => {
    await core.decline(deps);
    await refresh();
  }, [refresh]);

  return { ...view, turnOn, turnOff, notNow };
}

/** When one request is removed from the phone: stop notifications for it. Never throws. */
export async function unregisterSaved(item: { token: string }): Promise<void> {
  try {
    if ((await core.getState(deps)) !== 'on') return;
    const pushToken = await deps.getPushToken();
    if (pushToken) await pushUnregister(item.token, pushToken);
  } catch {
    // The server clears it when the request ends.
  }
}

/** When every saved request is removed: take this phone off all of them first. Never throws. */
export async function unregisterAllSaved(): Promise<void> {
  try {
    if ((await core.getState(deps)) === 'on') await core.disable(deps);
  } catch {
    // The server clears each when its request ends.
  }
}

/** After a request is saved (or added from a link): register it when notifications are on. */
export function registerSaved(item: { token: string }): Promise<boolean> {
  return core.registerNew(deps, item);
}
