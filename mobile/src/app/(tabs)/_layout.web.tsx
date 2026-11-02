// The web build exists for development and for rendering store screenshots; the shipped
// apps use the native tab bar in _layout.tsx.
import { Tabs } from 'expo-router';
import Svg, { Circle, Path } from 'react-native-svg';

import { usePalette } from '@/components/use-palette';
import { fonts } from '@/lib/theme';

function Icon({ name, color }: { name: 'home' | 'inbox' | 'more'; color: string }) {
  return (
    <Svg width={24} height={24} viewBox="0 0 24 24" fill="none" stroke={color} strokeWidth={1.9} strokeLinecap="round" strokeLinejoin="round">
      {name === 'home' ? <Path d="M4 11 12 4l8 7v8a1 1 0 0 1-1 1H5a1 1 0 0 1-1-1v-8ZM10 20v-6h4v6" /> : null}
      {name === 'inbox' ? <Path d="M4 13 6.5 5h11L20 13v6H4v-6Zm0 0h5l1 2h4l1-2h5" /> : null}
      {name === 'more' ? (
        <>
          <Circle cx={6} cy={12} r={1.2} />
          <Circle cx={12} cy={12} r={1.2} />
          <Circle cx={18} cy={12} r={1.2} />
        </>
      ) : null}
    </Svg>
  );
}

export default function TabsLayout() {
  const p = usePalette();
  return (
    <Tabs
      screenOptions={{
        headerShown: false,
        tabBarActiveTintColor: p.primary,
        tabBarInactiveTintColor: p.inkSoft,
        tabBarStyle: { backgroundColor: p.surface, borderTopColor: p.line, height: 64, paddingTop: 6 },
        tabBarLabelStyle: { fontFamily: fonts.bodyMedium, fontSize: 12 },
        sceneStyle: { backgroundColor: p.bg },
      }}>
      <Tabs.Screen name="index" options={{ title: 'Home', tabBarIcon: ({ color }) => <Icon name="home" color={String(color)} /> }} />
      <Tabs.Screen name="requests" options={{ title: 'Requests', tabBarIcon: ({ color }) => <Icon name="inbox" color={String(color)} /> }} />
      <Tabs.Screen name="more" options={{ title: 'More', tabBarIcon: ({ color }) => <Icon name="more" color={String(color)} /> }} />
    </Tabs>
  );
}
