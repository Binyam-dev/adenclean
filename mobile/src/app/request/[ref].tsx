import * as Haptics from 'expo-haptics';
import { router, useFocusEffect, useLocalSearchParams } from 'expo-router';
import { useCallback, useState } from 'react';
import { Linking, Platform, Pressable, StyleSheet, View } from 'react-native';

import { Notice, Rule, StatusPill } from '@/components/Bits';
import { Button } from '@/components/Button';
import { Field } from '@/components/Field';
import { Screen } from '@/components/Screen';
import { Stars } from '@/components/Stars';
import { Text } from '@/components/Text';
import { usePalette } from '@/components/use-palette';
import { ApiError, isGone, sendIssue, sendReview, statusCache, type Lookup } from '@/lib/api';
import { SUPPORT_EMAIL, SUPPORT_PHONE_DISPLAY, SUPPORT_PHONE_LINK } from '@/lib/config';
import { confirmAction } from '@/lib/confirm';
import { issueCopy, statusCopy } from '@/lib/status';
import { getSaved, removeRequest, type SavedRequest } from '@/lib/storage';
import { radius, space } from '@/lib/theme';
import { LIMITS, checkFeedback, clean, serviceTitle, speakDate, timeTitle } from '@/lib/validation';

type Load = 'loading' | 'ready' | 'offline' | 'gone' | 'missing';

export default function RequestDetail() {
  const p = usePalette();
  const { ref, sent } = useLocalSearchParams<{ ref: string; sent?: string }>();
  const reference = String(ref ?? '');

  const [saved, setSaved] = useState<SavedRequest | null>(null);
  const [info, setInfo] = useState<Lookup | null>(null);
  const [state, setState] = useState<Load>('loading');
  const [refreshing, setRefreshing] = useState(false);

  const [rating, setRating] = useState(0);
  const [review, setReview] = useState('');
  const [reviewError, setReviewError] = useState<string | null>(null);
  const [reviewBusy, setReviewBusy] = useState(false);
  const [reviewDone, setReviewDone] = useState(false);

  const [reporting, setReporting] = useState(false);
  const [issue, setIssue] = useState('');
  const [issueError, setIssueError] = useState<string | null>(null);
  const [issueBusy, setIssueBusy] = useState(false);

  const load = useCallback(async (force = false) => {
    const item = await getSaved(reference);
    if (!item) {
      setState('missing');
      return;
    }
    setSaved(item);
    try {
      setInfo(await statusCache.get(item.token, force));
      setState('ready');
    } catch (e) {
      setState(isGone(e) ? 'gone' : 'offline');
    }
  }, [reference]);

  useFocusEffect(
    useCallback(() => {
      void load();
    }, [load]),
  );

  const onRefresh = async () => {
    setRefreshing(true);
    await load(true);
    setRefreshing(false);
  };

  const success = () => {
    if (Platform.OS !== 'web') void Haptics.notificationAsync(Haptics.NotificationFeedbackType.Success);
  };

  const submitReview = async () => {
    if (!saved) return;
    if (rating < 1) {
      setReviewError('Choose a rating from 1 to 5 stars.');
      return;
    }
    const problem = checkFeedback(review);
    if (problem) {
      setReviewError(problem);
      return;
    }
    setReviewError(null);
    setReviewBusy(true);
    try {
      await sendReview(saved.token, rating, review);
      success();
      setReviewDone(true);
      statusCache.forget(saved.token);
      setInfo((current) => (current ? { ...current, reviewSubmitted: true } : current));
    } catch (e) {
      setReviewError(e instanceof ApiError ? e.message : "We couldn't send your review. Try again.");
    } finally {
      setReviewBusy(false);
    }
  };

  const submitIssue = async () => {
    if (!saved) return;
    const problem = checkFeedback(issue);
    if (problem) {
      setIssueError(problem);
      return;
    }
    setIssueError(null);
    setIssueBusy(true);
    try {
      await sendIssue(saved.token, issue);
      success();
      setReporting(false);
      statusCache.forget(saved.token);
      setInfo((current) => (current ? { ...current, issueSubmitted: true, issueStatus: 'open' } : current));
    } catch (e) {
      setIssueError(e instanceof ApiError ? e.message : "We couldn't send your report. Try again.");
    } finally {
      setIssueBusy(false);
    }
  };

  const forget = async () => {
    const yes = await confirmAction({
      title: 'Remove this request from your phone?',
      message: "You won't be able to check its status or leave feedback here. AdenClean keeps the request it already received.",
      confirmLabel: 'Remove request',
      cancelLabel: 'Keep request',
      destructive: true,
    });
    if (!yes) return;
    await removeRequest(reference);
    router.dismissTo('/requests');
  };

  const copy = info ? statusCopy(info.status) : null;

  return (
    <Screen refreshing={refreshing} onRefresh={onRefresh}>
      <Pressable
        accessibilityRole="button"
        accessibilityLabel="Back to your requests"
        onPress={() => router.dismissTo('/requests')}
        style={styles.back}>
        <Text variant="bodyStrong" tone="primary">
          Back to requests
        </Text>
      </Pressable>

      {state === 'missing' ? (
        <Notice kind="info" title="This request isn't on this phone">
          It may have been removed, or sent from another device. You can send a new request any time.
        </Notice>
      ) : null}

      {saved ? (
        <View style={{ gap: space.xs }}>
          <Text variant="title" accessibilityRole="header">
            {serviceTitle(saved.service)}
          </Text>
          <Text variant="body" tone="soft">
            {saved.time ? `${speakDate(saved.date)}, ${timeTitle(saved.time).toLowerCase()}` : speakDate(saved.date)}
          </Text>
        </View>
      ) : null}

      {sent === '1' ? (
        <Notice kind="success" title="Request sent">
          AdenClean has it. This isn&apos;t a confirmed booking, and you can check its status here at any time.
        </Notice>
      ) : null}

      {state === 'loading' ? <Text variant="body" tone="soft">Checking status…</Text> : null}

      {state === 'offline' ? (
        <Notice kind="error" title="Can't check the status right now">
          Your request is safe. Check your connection, then pull down to try again.
        </Notice>
      ) : null}

      {state === 'gone' ? (
        <Notice kind="error" title="AdenClean can't find this request">
          {`It may have been removed. Email ${SUPPORT_EMAIL} if you expected to see it here.`}
        </Notice>
      ) : null}

      {copy ? (
        <View style={[styles.card, { backgroundColor: p.surface, borderColor: p.line }]}>
          <StatusPill label={copy.label} tone={copy.tone} />
          <Text variant="body">{copy.detail}</Text>
          {saved?.imported ? null : (
            <>
              <Rule />
              <Text variant="caption" tone="soft">
                Reference
              </Text>
              <Text variant="bodyStrong" selectable>
                {reference}
              </Text>
            </>
          )}
        </View>
      ) : null}

      {info && !info.ready && state === 'ready' ? (
        <View style={[styles.card, { backgroundColor: p.surfaceDeep, borderColor: 'transparent' }]}>
          <Text variant="heading">Feedback opens after your service</Text>
          <Text variant="small" tone="soft">
            Reviews and problem reports become available once AdenClean marks the service complete.
          </Text>
        </View>
      ) : null}

      {info && info.ready ? (
        <>
          <View style={[styles.card, { backgroundColor: p.surface, borderColor: p.line }]}>
            <Text variant="heading">Your review</Text>
            {info.reviewSubmitted ? (
              <Text variant="body" tone="success">
                {reviewDone ? 'Thank you. Your review was sent.' : 'You sent a review for this service. Thank you.'}
              </Text>
            ) : (
              <>
                <Text variant="small" tone="soft">
                  AdenClean reads reviews privately. They aren&apos;t posted publicly.
                </Text>
                <Stars value={rating} onChange={setRating} />
                <Field
                  label="What was it like?"
                  multiline
                  value={review}
                  onChangeText={setReview}
                  maxLength={LIMITS.feedback + 100}
                  counter={`${clean(review, true).length} of ${LIMITS.feedback}`}
                  error={reviewError}
                  showError={!!reviewError}
                />
                <Button label="Send review" onPress={() => void submitReview()} loading={reviewBusy} />
              </>
            )}
          </View>

          <View style={[styles.card, { backgroundColor: p.surface, borderColor: p.line }]}>
            <Text variant="heading">Something went wrong?</Text>
            {info.issueSubmitted ? (
              <Text variant="body">{issueCopy(info.issueStatus)}</Text>
            ) : reporting ? (
              <>
                <Field
                  label="What happened?"
                  multiline
                  value={issue}
                  onChangeText={setIssue}
                  maxLength={LIMITS.feedback + 100}
                  counter={`${clean(issue, true).length} of ${LIMITS.feedback}`}
                  error={issueError}
                  showError={!!issueError}
                />
                <Button label="Send report" onPress={() => void submitIssue()} loading={issueBusy} />
                <Button label="Cancel" variant="quiet" onPress={() => setReporting(false)} disabled={issueBusy} />
              </>
            ) : (
              <>
                <Text variant="small" tone="soft">
                  Tell AdenClean about a problem with the service. You can send one report per request.
                </Text>
                <Button label="Report a problem" variant="secondary" onPress={() => setReporting(true)} />
              </>
            )}
          </View>
        </>
      ) : null}

      <View style={[styles.card, { backgroundColor: p.surface, borderColor: p.line }]}>
        <Text variant="heading">Need to talk to someone?</Text>
        <Button label={`Call ${SUPPORT_PHONE_DISPLAY}`} variant="secondary" onPress={() => void Linking.openURL(SUPPORT_PHONE_LINK)} />
        <Button label="Send an email" variant="secondary" onPress={() => void Linking.openURL(`mailto:${SUPPORT_EMAIL}?subject=${encodeURIComponent(`AdenClean request ${reference}`)}`)} />
      </View>

      {saved ? <Button label="Remove from this phone" variant="quiet" onPress={() => void forget()} /> : null}
    </Screen>
  );
}

const styles = StyleSheet.create({
  back: { minHeight: 48, justifyContent: 'center', alignSelf: 'flex-start' },
  card: { borderRadius: radius.card, borderWidth: 1.5, padding: space.xl, gap: space.md },
});
