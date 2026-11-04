"""Marketplace rules: job states, offers, money and double-acceptance."""

import sys
import threading
import unittest
from datetime import datetime, timedelta, timezone
from itertools import product
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from marketplace import config as mconfig  # noqa: E402
from marketplace import jobs, locks, money, offers  # noqa: E402

CFG = mconfig.MarketplaceConfig()
ACTORS = (jobs.CUSTOMER, jobs.CLEANER, jobs.ADMIN, jobs.SYSTEM)


class JobStateTests(unittest.TestCase):
    def test_every_pair_and_actor_matches_the_table(self):
        for current, target, actor in product(sorted(jobs.STATES), sorted(jobs.STATES), ACTORS):
            allowed = actor in jobs.TRANSITIONS.get((current, target), ()) and current not in jobs.TERMINAL
            with self.subTest(current=current, target=target, actor=actor):
                if allowed:
                    self.assertEqual(jobs.transition(current, target, actor), target)
                else:
                    with self.assertRaises(jobs.TransitionError):
                        jobs.transition(current, target, actor)

    def test_happy_path(self):
        state = "draft"
        for target, actor in [("open", jobs.CUSTOMER), ("booked", jobs.CUSTOMER),
                              ("in_progress", jobs.CLEANER), ("awaiting_confirmation", jobs.CLEANER),
                              ("completed", jobs.SYSTEM)]:
            state = jobs.transition(state, target, actor)
        self.assertEqual(state, "completed")

    def test_terminal_states_never_change(self):
        for state in jobs.TERMINAL:
            self.assertEqual(jobs.next_states(state, jobs.ADMIN), [])

    def test_unknown_state_rejected(self):
        with self.assertRaises(jobs.TransitionError):
            jobs.transition("open", "paid", jobs.CUSTOMER)

    def test_only_the_system_expires_jobs_and_no_one_assigns_them(self):
        self.assertEqual(jobs.TRANSITIONS[("open", "expired")], {jobs.SYSTEM})
        # Booking happens only when the customer accepts; the platform never assigns work.
        self.assertEqual(jobs.TRANSITIONS[("open", "booked")], {jobs.CUSTOMER})


def open_job(customer="cust-1"):
    return {"id": "job-1", "customer_id": customer, "status": "open"}


class OfferTests(unittest.TestCase):
    def test_cleaner_sets_the_price(self):
        offer, flags = offers.make_offer("o1", open_job(), "cleaner-1", 12_000, CFG)
        self.assertEqual(offer.price_cents, 12_000)
        self.assertEqual(offer.awaiting, jobs.CUSTOMER)
        self.assertEqual(flags, [])

    def test_price_must_be_whole_cents_in_range(self):
        for bad in (12_000.5, "12000", True, CFG.min_price_cents - 1, CFG.max_price_cents + 1):
            with self.subTest(bad=bad), self.assertRaises(offers.OfferError):
                offers.make_offer("o1", open_job(), "cleaner-1", bad, CFG)

    def test_no_offers_on_your_own_job(self):
        with self.assertRaises(offers.OfferError):
            offers.make_offer("o1", open_job("same-person"), "same-person", 12_000, CFG)

    def test_soft_self_dealing_signals_are_flagged_not_blocked(self):
        _, flags = offers.make_offer("o1", open_job(), "cleaner-1", 12_000, CFG,
                                     signals={"same_device": True, "same_address": False})
        self.assertEqual(flags, ["same_device"])

    def test_no_offers_on_a_closed_job(self):
        job = dict(open_job(), status="booked")
        with self.assertRaises(offers.OfferError):
            offers.make_offer("o1", job, "cleaner-1", 12_000, CFG)

    def test_counters_alternate_and_stop_after_the_limit(self):
        offer, _ = offers.make_offer("o1", open_job(), "cleaner-1", 15_000, CFG)
        offer = offers.counter(offer, jobs.CUSTOMER, 12_000, CFG)
        self.assertEqual(offer.awaiting, jobs.CLEANER)
        with self.assertRaises(offers.OfferError):  # not the customer's turn
            offers.counter(offer, jobs.CUSTOMER, 11_000, CFG)
        offer = offers.counter(offer, jobs.CLEANER, 13_500, CFG)
        self.assertEqual(offer.counter_rounds, 2)
        with self.assertRaises(offers.OfferError):  # limit reached
            offers.counter(offer, jobs.CUSTOMER, 13_000, CFG)
        accepted = offers.accept(offer, jobs.CUSTOMER)
        self.assertEqual((accepted.status, accepted.price_cents), (offers.ACCEPTED, 13_500))

    def test_price_locks_at_acceptance(self):
        offer, _ = offers.make_offer("o1", open_job(), "cleaner-1", 15_000, CFG)
        accepted = offers.accept(offer, jobs.CUSTOMER)
        for action in (lambda: offers.counter(accepted, jobs.CLEANER, 20_000, CFG),
                       lambda: offers.accept(accepted, jobs.CUSTOMER),
                       lambda: offers.withdraw(accepted, "cleaner-1")):
            with self.assertRaises(offers.OfferError):
                action()

    def test_only_the_sender_withdraws(self):
        offer, _ = offers.make_offer("o1", open_job(), "cleaner-1", 15_000, CFG)
        with self.assertRaises(offers.OfferError):
            offers.withdraw(offer, "cleaner-2")
        self.assertEqual(offers.withdraw(offer, "cleaner-1").status, offers.WITHDRAWN)

    def test_declining_has_no_side_effects_beyond_the_offer(self):
        offer, _ = offers.make_offer("o1", open_job(), "cleaner-1", 15_000, CFG)
        declined = offers.decline(offer, jobs.CUSTOMER)
        self.assertEqual(declined.status, offers.DECLINED)
        self.assertEqual(set(vars(declined)) - set(vars(offer)), set())  # no penalty fields


class MoneyTests(unittest.TestCase):
    def test_split_uses_integer_cents_and_gives_tips_to_the_cleaner(self):
        split = money.split_payment(12_345, CFG, tip_cents=1_000)
        self.assertEqual(split["platform_fee_cents"], 1_852)  # 15% of 123.45 = 18.5175 -> 18.52
        self.assertEqual(split["cleaner_payout_cents"], 12_345 - 1_852 + 1_000)
        self.assertEqual(split["customer_pays_cents"], 13_345)
        self.assertEqual(split["platform_fee_cents"] + split["cleaner_payout_cents"], split["customer_pays_cents"])
        self.assertTrue(all(isinstance(v, int) for v in split.values()))

    def test_negative_amounts_rejected(self):
        with self.assertRaises(ValueError):
            money.split_payment(-1, CFG)
        with self.assertRaises(ValueError):
            money.split_payment(100, CFG, tip_cents=-5)

    def test_cancellation_rules(self):
        start = datetime(2026, 12, 1, 10, tzinfo=timezone.utc)
        early = start - timedelta(hours=25)
        late = start - timedelta(hours=3)
        self.assertEqual(money.cancellation(10_000, "customer", early, start, CFG)["cleaner_fee_cents"], 0)
        late_customer = money.cancellation(10_000, "customer", late, start, CFG)
        self.assertEqual((late_customer["cleaner_fee_cents"], late_customer["refund_cents"]), (2_500, 7_500))
        self.assertEqual(money.cancellation(10_000, "customer", late, start, CFG, waived=True)["cleaner_fee_cents"], 0)
        cleaner_late = money.cancellation(10_000, "cleaner", late, start, CFG)
        self.assertEqual((cleaner_late["refund_cents"], cleaner_late["cleaner_fee_cents"]), (10_000, 0))

    def test_auto_confirm_after_48_hours(self):
        out = datetime(2026, 12, 1, 12, tzinfo=timezone.utc)
        self.assertFalse(money.auto_confirm_due(out, out + timedelta(hours=47, minutes=59), CFG))
        self.assertTrue(money.auto_confirm_due(out, out + timedelta(hours=48), CFG))


class ConfigTests(unittest.TestCase):
    def test_env_overrides_and_validation(self):
        cfg = mconfig.load({"PLATFORM_FEE_BPS": "1000", "SERVICE_ZIPS": "20910, 20912"})
        self.assertEqual((cfg.platform_fee_bps, cfg.service_zips), (1000, ("20910", "20912")))
        with self.assertRaises(ValueError):
            mconfig.load({"PLATFORM_FEE_BPS": "10001"})
        with self.assertRaises(ValueError):
            mconfig.load({"MAX_COUNTER_ROUNDS": "-1"})


class DoubleAcceptanceTests(unittest.TestCase):
    """Many customers' taps race to accept different offers on one job; exactly one wins."""

    def test_one_job_books_exactly_once_under_concurrency(self):
        job = {"id": "job-1", "customer_id": "cust-1", "status": "open"}
        store = {"job": job, "offers": {}}
        for i in range(20):
            offer, _ = offers.make_offer(f"o{i}", job, f"cleaner-{i}", 10_000 + i, CFG)
            store["offers"][offer.id] = offer
        saves = []

        def load_job(_):
            return dict(store["job"])

        def load_offer(offer_id):
            return store["offers"][offer_id]

        def save(new_job, new_offer):
            store["job"] = new_job
            store["offers"][new_offer.id] = new_offer
            saves.append(new_offer.id)

        barrier = threading.Barrier(20)
        results = []

        def attempt(offer_id):
            barrier.wait()
            try:
                locks.accept_offer(load_job, load_offer, save, offer_id, "cust-1", jobs.CUSTOMER)
                results.append("ok")
            except offers.OfferError:
                results.append("rejected")

        threads = [threading.Thread(target=attempt, args=(f"o{i}",)) for i in range(20)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        self.assertEqual(results.count("ok"), 1)
        self.assertEqual(len(saves), 1)
        self.assertEqual(store["job"]["status"], "booked")
        self.assertEqual(store["job"]["booked_offer_id"], saves[0])

    def test_only_the_job_owner_can_accept(self):
        job = {"id": "job-1", "customer_id": "cust-1", "status": "open"}
        offer, _ = offers.make_offer("o1", job, "cleaner-1", 10_000, CFG)
        with self.assertRaises(offers.OfferError):
            locks.accept_offer(lambda _: job, lambda _: offer, lambda *a: None, "o1", "someone-else", jobs.CUSTOMER)


if __name__ == "__main__":
    unittest.main()
