import { router } from 'expo-router';
import { Pressable, StyleSheet, View } from 'react-native';

import { Wordmark } from '@/components/Bits';
import { Button } from '@/components/Button';
import { House } from '@/components/House';
import { Screen } from '@/components/Screen';
import { Text } from '@/components/Text';
import { usePalette } from '@/components/use-palette';
import { SERVICE_AREA } from '@/lib/config';
import { radius, space } from '@/lib/theme';
import { SERVICES } from '@/lib/validation';

const STEPS = [
  { title: 'Send a request', body: 'Choose a service, a day and a time that suit you.' },
  { title: 'AdenClean reviews it', body: 'Each request is looked at before anything is arranged.' },
  { title: 'We follow up', body: 'AdenClean talks through the details with you. Nothing is booked until then.' },
];

export default function Home() {
  const p = usePalette();

  return (
    <Screen>
      <View style={[styles.hero, { backgroundColor: p.hero }]}>
        <Wordmark onHero />
        <View style={styles.houseWrap}>
          <House lit={[true, true, true, true]} introduce size={236} tone="hero" />
        </View>
        <View style={styles.heroText}>
          <Text variant="display" tone="onHero" accessibilityRole="header">
            A little more at ease at home.
          </Text>
          <Text variant="body" tone="heroSoft">
            Tell us what needs cleaning and when. AdenClean reviews each request.
          </Text>
        </View>
        <Button label="Request a cleaning" variant="onHero" onPress={() => router.push('/new')} />
      </View>

      <View style={styles.section}>
        <Text variant="title" accessibilityRole="header">
          What we can help with
        </Text>
        <View style={styles.list}>
          {SERVICES.map((service) => (
            <Pressable
              key={service.id}
              accessibilityRole="button"
              accessibilityLabel={`${service.title}. ${service.tagline}. Start a request`}
              onPress={() => router.push({ pathname: '/new', params: { service: service.id } })}
              style={({ pressed }) => [
                styles.service,
                { backgroundColor: p.surface, borderColor: p.line, opacity: pressed ? 0.9 : 1 },
              ]}>
              <Text variant="heading">{service.title}</Text>
              <Text variant="bodyStrong" tone="primary">
                {service.tagline}
              </Text>
              <Text variant="small" tone="soft">
                {service.description}
              </Text>
            </Pressable>
          ))}
        </View>
      </View>

      <View style={[styles.section, styles.how, { backgroundColor: p.surfaceDeep }]}>
        <Text variant="title" accessibilityRole="header">
          How it works
        </Text>
        <View style={styles.list}>
          {STEPS.map((step, index) => (
            <View key={step.title} style={styles.step}>
              <View style={[styles.stepNumber, { backgroundColor: p.primary }]}>
                <Text variant="bodyStrong" tone="onPrimary">
                  {index + 1}
                </Text>
              </View>
              <View style={styles.stepText}>
                <Text variant="bodyStrong">{step.title}</Text>
                <Text variant="small" tone="soft">
                  {step.body}
                </Text>
              </View>
            </View>
          ))}
        </View>
      </View>

      <Text variant="small" tone="soft" style={styles.footnote}>
        Now serving {SERVICE_AREA}. A request is an inquiry, not a confirmed booking.
      </Text>
    </Screen>
  );
}

const styles = StyleSheet.create({
  hero: {
    borderRadius: radius.hero,
    padding: space.xl,
    gap: space.xl,
    overflow: 'hidden',
  },
  houseWrap: { alignSelf: 'flex-end', marginRight: -34, marginTop: -4, marginBottom: -12 },
  heroText: { gap: space.md },
  section: { gap: space.lg },
  list: { gap: space.md },
  service: {
    borderRadius: radius.card,
    borderWidth: 1.5,
    padding: space.xl,
    gap: 6,
    minHeight: 48,
  },
  how: { borderRadius: radius.hero - 4, padding: space.xl },
  step: { flexDirection: 'row', gap: space.lg, alignItems: 'flex-start' },
  stepNumber: { width: 32, height: 32, borderRadius: 16, alignItems: 'center', justifyContent: 'center' },
  stepText: { flex: 1, gap: 2 },
  footnote: { textAlign: 'left' },
});
