import { router, useFocusEffect } from 'expo-router';
import { useCallback, useState } from 'react';

import { Notice, Wordmark } from '@/components/Bits';
import { Button } from '@/components/Button';
import { EmptyState, Segmented } from '@/components/Controls';
import { JobCard } from '@/components/JobCard';
import { Screen } from '@/components/Screen';
import { Text } from '@/components/Text';
import { ApiError } from '@/lib/api';
import { SUPPORT_EMAIL } from '@/lib/config';
import { signOut, useSession } from '@/lib/session';
import { isSignedOut, type Job } from '@/lib/v1';

type Mode = 'hire' | 'work';

/** One account, two modes: Hire (post jobs, pick offers) and Work (find jobs, send offers). */
export default function Market() {
  const { user, loaded, client } = useSession();
  const [mode, setMode] = useState<Mode>('hire');
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
        <Wordmark />
        <Text variant="title" accessibilityRole="header">Hire a cleaner, or find cleaning work</Text>
        <Text tone="soft">
          Post a job and compare offers from local cleaners. Or, if you clean, see jobs near you and name your own price.
        </Text>
        <Button label="Sign in or create an account" onPress={() => router.push('/sign-in')} testID="market-signin" />
        <Text variant="small" tone="soft">One account works for both. No password: we email you a code.</Text>
      </Screen>
    );
  }

  const greeting = user.displayName ? `Hi, ${user.displayName}` : 'Hi';

  return (
    <Screen
      refreshing={refreshing}
      onRefresh={async () => {
        setRefreshing(true);
        await load();
        setRefreshing(false);
      }}>
      <Text variant="small" tone="soft">{greeting}</Text>
      <Segmented<Mode> label="Mode" value={mode} onChange={setMode}
        options={[{ id: 'hire', title: 'Hire' }, { id: 'work', title: 'Work' }]} />
      <Text variant="title" accessibilityRole="header">
        {mode === 'hire' ? 'Your jobs' : 'Jobs near you'}
      </Text>

      {mode === 'hire' && jobs && jobs.length > 0 ? (
        <Button label="Post a cleaning job" onPress={() => router.push('/job/new')} testID="market-post" />
      ) : null}
      {mode === 'work' && isCleaner ? (
        <Text tone="soft">You choose which jobs to answer and name your own price. Passing on a job never counts against you.</Text>
      ) : null}

      {error ? <Notice kind="error">{error}</Notice> : null}
      {jobs === null && !error ? <Text tone="soft">Loading…</Text> : null}

      {mode === 'hire' && jobs?.length === 0 ? (
        <EmptyState
          title="Post your first job"
          body="Say what needs cleaning and when. Cleaners nearby send offers with their own price, and you choose."
          action={<Button label="Post a cleaning job" onPress={() => router.push('/job/new')} testID="market-post" />}
        />
      ) : null}
      {mode === 'work' && !isCleaner ? (
        <EmptyState
          title="Clean with AdenClean"
          body={`AdenClean reviews every cleaner before they can see jobs. Email ${SUPPORT_EMAIL} to apply. You set your prices and choose your jobs.`}
        />
      ) : null}
      {mode === 'work' && isCleaner && jobs?.length === 0 ? (
        <EmptyState title="No open jobs right now" body="New jobs in your area appear here. Pull down to check again." />
      ) : null}

      {jobs?.map((job) => (
        <JobCard key={job.id} job={job} showStatus={mode === 'hire'} onPress={() => router.push(`/job/${job.id}`)} />
      ))}
    </Screen>
  );
}
