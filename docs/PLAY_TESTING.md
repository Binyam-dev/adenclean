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

Where: communities for closed-test swaps, for example r/AndroidClosedTesting. [Guessing: it exists and is the usual place; confirm it, read its rules and flair requirements before posting.]

**Title:** Looking for 20 Android testers for a small home-cleaning request app (14-day Play closed test, happy to test yours back)

**Body:**

> I'm a solo developer launching AdenClean, a simple app for requesting a home cleaning in Silver Spring, MD. Google requires 12+ testers opted in for 14 days before I can publish.
>
> What I need: an Android phone (Android 7 or newer), a Google account, and about 5 minutes to try it, then staying opted in for 14 days. No sign-up in the app, no payment, no personal info needed: use made-up details.
>
> What you get: my honest feedback on your app too. Comment or message me your Play account email and the app you'd like tested, and I'll add you and test yours in return.
>
> Opt-in link and steps will be sent once you comment. Thank you!

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
