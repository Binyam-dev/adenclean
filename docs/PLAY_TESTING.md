# Google Play closed testing: recruiting and running the 14 days

Nothing in this file has been posted. The Reddit post needs the owner's explicit yes, and the subreddit's own rules must be read first.

## The requirement

At least 12 testers opted in, continuously, for 14 days, in a **closed** test (not internal testing). Then apply for production access. Aim for **20 or more** opted-in testers, because dropouts reset those people's days and the clock needs 12 at all times. Source: support.google.com/googleplay/android-developer/answer/14151465.

## Set up the test (owner, in Play Console)

1. Testing > Closed testing > Create track (name it "Beta").
2. Upload the `.aab` (EAS build page, Android build) and roll out to the track.
3. Testers tab > create a tester list (or use a Google Group) and add yourself first.
4. Copy the **opt-in link** from the track page. Anyone on the list who opens it can join and install.
5. Add every tester email you receive to the list. Keep those emails private: do not put them in the repository.

## Tester instructions (send to each tester, or paste in a reply)

> Thanks for helping test AdenClean, a small app for requesting a home cleaning in Silver Spring, Maryland. It takes about 5 minutes the first time.
>
> 1. On your Android phone, open this link while signed in to the Google account you gave me: **PASTE OPT-IN LINK**. Tap "Become a tester", then "Download it on Google Play" and install the app.
> 2. Open AdenClean and tap "Request a cleaning". Pick any service and day, enter any name, an email address and "Silver Spring", agree, and send. Please don't enter your real address or phone number. You will not be contacted.
> 3. Open the Requests tab and check your request's status. Try the app on cellular as well as Wi-Fi if you can.
> 4. Tell me anything confusing, broken or ugly. Replying with one line is fine.
>
> **Please stay opted in for 14 days** (until **FILL IN DATE**) and leave the app installed. Google requires this, and I can't proceed to launch if enough people drop out. Opening the app once or twice during that time helps too. Thank you!

## Reddit recruitment post (draft, do not post without the owner's yes)

Where: r/AndroidClosedTesting. [Certain: it exists and is active as of 2026-11-13; its posts are test-for-test swaps.] I could not read its sidebar rules, so open the subreddit and check them and any flair requirement before posting. [Likely] posts there put the Google Group and opt-in links in the post itself and say "I test back"; the draft follows that style.

**Title:** [T4T] Need 20 testers for AdenClean (home-cleaning request app), 14-day closed test. I test yours back!

**Body** (replace the two PASTE lines once the closed track exists; do not post before then):

> Hi! I'm a solo developer launching AdenClean, a simple app for requesting a home cleaning in Silver Spring, MD. Google needs 12+ testers opted in for 14 days before I can publish.
>
> **How to join (about 5 minutes):**
> 1. Join the Google Group: **PASTE GROUP LINK**
> 2. Become a tester: **PASTE OPT-IN LINK**
> 3. Install AdenClean from Google Play, tap "Request a cleaning" and send a request with made-up details (no real address or phone).
> 4. Please stay opted in for 14 days (until **FILL IN DATE**).
>
> **What you need:** an Android phone (Android 7 or newer: verify the app's minimum before posting) and a Google account. No sign-up in the app, no payment, nothing is sent to you.
>
> **I test back:** comment with your app's link (or DM me) and I'll install it, keep it for 14 days and leave honest feedback. Thank you!

Optional: attach one screenshot, or the promo video's first frame, as the post image (many swap posts do).

Both links are the same for every tester, so nobody needs to send me an email address; the Google Group handles the tester list. Reply to each commenter with the tester instructions above and keep any private details out of the public thread.

Reply to each commenter with the tester instructions above, ask for their Play email by private message (never in public comments), and add it to the tester list.

## Tracking (keep `RELEASE.md` current)

- Record the day 12 or more are opted in as the **clock start date**. Day 14 is clock start plus 14 days.
- Check the opted-in count every other day and add a row to the count table. If it falls below 12, the clock effectively restarts for the missing testers: invite more at once.
- Message the group around day 3, day 7 and day 12 with a short reminder to stay opted in.
- Ship one real update during the test (planned: 1.0.1 with push notifications), and log it.
- Log every piece of feedback and what you did about it. The production application asks about testing and feedback. [Likely: Google's form asks how you recruited testers, what feedback you received and what you changed; read the form before you start so the log has the right detail.]

## If a tester asks

- "Is it free?" Yes. No ads. No payment.
- "What data does it collect?" Only what you type into the request form (name, email, town or ZIP, notes), sent over HTTPS to the AdenClean server. Privacy policy: https://adenclean.onrender.com/policies.html#privacy
- "How do I leave?" Open the same opt-in link and choose "Leave the test", or uninstall. Please wait until day 14 if you can.
