import { router, useFocusEffect } from 'expo-router';
import { useCallback, useState } from 'react';
import { View } from 'react-native';

import { Notice } from '@/components/Bits';
import { Button } from '@/components/Button';
import { Chip } from '@/components/Choice';
import { JobCard } from '@/components/JobCard';
import { Screen } from '@/components/Screen';
import { Text } from '@/components/Text';
import { ApiError } from '@/lib/api';
import { SUPPORT_EMAIL } from '@/lib/config';
import { signOut, useSession } from '@/lib/session';
import { space } from '@/lib/theme';
import { isSignedOut, type Job } from '@/lib/v1';

/** One account, two modes: Hire (post jobs, pick offers) and Work (find jobs, send offers). */
export default function Market() {
  const { user, loaded, client } = useSession();
  const [mode, setMode] = useState<'hire' | 'work'>('hire');
  const [jobs, setJobs] = useState<Job[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [refreshing, setRefreshing] = useState(false);
  const isCleaner = !!user?.roles.includes('cleaner');

  const load = useCallback(async () => {
    if (!user) return;
    setError(null);
    try {
      setJobs(mode === 'hire' ? await client.myJobs() : isCleaner ? await client.openJobs() : []);
    } catch (e) {
      if (isSignedOut(e)) await signOut();
      else setError(e instanceof ApiError ? e.message : 'Could not load jobs.');
    }
    // client changes identity each render; the token is what matters.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [user?.id, mode, isCleaner]);

  useFocusEffect(
    useCallback(() => {
      setJobs(null);
      void load();
    }, [load]),
  );

  if (!loaded) return <Screen><Text tone="soft">Loading…</Text></Screen>;

  if (!user) {
    return (
      <Screen>
        <Text variant="title" accessibilityRole="header">Hire or work</Text>
        <Text tone="soft">
          Post a cleaning job and choose from offers by local cleaners, or find jobs near you and name your own price.
        </Text>
        <Button label="Sign in or create an account" onPress={() => router.push('/sign-in')} testID="market-signin" />
      </Screen>
    );
  }

  return (
    <Screen
      refreshing={refreshing}
      onRefresh={async () => {
        setRefreshing(true);
        await load();
        setRefreshing(false);
      }}>
      <Text variant="title" accessibilityRole="header">
        {mode === 'hire' ? 'Your jobs' : 'Jobs near you'}
      </Text>
      <View style={{ flexDirection: 'row', gap: space.sm }} accessibilityRole="radiogroup">
        <Chip label="Hire" selected={mode === 'hire'} onPress={() => setMode('hire')} />
        <Chip label="Work" selected={mode === 'work'} onPress={() => setMode('work')} />
      </View>

      {mode === 'hire' ? (
        <Button label="Post a cleaning job" onPress={() => router.push('/job/new')} testID="market-post" />
      ) : !isCleaner ? (
        <Notice title="Want to clean with AdenClean?">
          {`Cleaners are checked before they can see jobs. Email ${SUPPORT_EMAIL} to apply. You set your own prices and choose which jobs to take.`}
        </Notice>
      ) : (
        <Text tone="soft">You choose which jobs to answer and name your own price. Ignoring a job never counts against you.</Text>
      )}

      {error ? <Notice kind="error">{error}</Notice> : null}
      {jobs === null ? <Text tone="soft">Loading…</Text> : null}
      {jobs && jobs.length === 0 && (mode === 'hire' || isCleaner) ? (
        <Text tone="soft">{mode === 'hire' ? 'No jobs yet.' : 'No open jobs in your area right now. Pull down to check again.'}</Text>
      ) : null}
      {jobs?.map((job) => (
        <JobCard key={job.id} job={job} showStatus={mode === 'hire'} onPress={() => router.push(`/job/${job.id}`)} />
      ))}
    </Screen>
  );
}
