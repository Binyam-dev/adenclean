import { NativeTabs } from 'expo-router/native-tabs';

import { usePalette } from '@/components/use-palette';

export default function TabsLayout() {
  const p = usePalette();
  return (
    <NativeTabs
      tintColor={p.primary}
      iconColor={{ default: p.inkSoft, selected: p.primary }}
      labelStyle={{ default: { color: p.inkSoft }, selected: { color: p.primary } }}
      backgroundColor={p.surface}
      indicatorColor={p.accent}>
      <NativeTabs.Trigger name="index">
        <NativeTabs.Trigger.Label>Home</NativeTabs.Trigger.Label>
        <NativeTabs.Trigger.Icon sf={{ default: 'house', selected: 'house.fill' }} md="home" />
      </NativeTabs.Trigger>
      <NativeTabs.Trigger name="requests">
        <NativeTabs.Trigger.Label>Requests</NativeTabs.Trigger.Label>
        <NativeTabs.Trigger.Icon sf={{ default: 'tray', selected: 'tray.fill' }} md="inbox" />
      </NativeTabs.Trigger>
      <NativeTabs.Trigger name="more">
        <NativeTabs.Trigger.Label>More</NativeTabs.Trigger.Label>
        <NativeTabs.Trigger.Icon sf={{ default: 'ellipsis.circle', selected: 'ellipsis.circle.fill' }} md="more_horiz" />
      </NativeTabs.Trigger>
    </NativeTabs>
  );
}
