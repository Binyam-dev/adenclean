"""Vetting rules: FCRA order of operations, individualized assessment, waiting period."""

import sys
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from marketplace import vetting as v  # noqa: E402

MON = datetime(2026, 11, 2, 15, tzinfo=timezone.utc)  # a Monday
NOTE = "Theft conviction in 2024, two years ago; this work means unsupervised access to homes."


def reviewed(result="consider"):
    r = v.new_record("u1", MON)
    r = v.record_consent(r, "Hana Tesfaye", True, MON)
    r = dict(r, background_status="pending", candidate_ref="cand_1")
    r = v.apply_identity_result(r, True, MON)
    return v.apply_background_result(r, result, "rpt_1", MON)


class VettingRuleTests(unittest.TestCase):
    def test_no_report_before_signed_authorization(self):
        r = v.new_record("u1", MON)
        with self.assertRaises(v.VettingError):
            v.can_order_background(r)
        with self.assertRaises(v.VettingError):
            v.record_consent(r, "Hana Tesfaye", False, MON)
        with self.assertRaises(v.VettingError):
            v.record_consent(r, "  ", True, MON)
        signed = v.record_consent(r, "Hana Tesfaye", True, MON)
        self.assertEqual(signed["disclosure_version"], v.DISCLOSURE_VERSION)
        v.can_order_background(signed)  # now allowed

    def test_review_starts_only_when_both_checks_are_back(self):
        r = v.record_consent(v.new_record("u1", MON), "Hana Tesfaye", True, MON)
        r = v.apply_identity_result(r, True, MON)
        self.assertEqual(r["status"], "applied")
        r = v.apply_background_result(r, "clear", "rpt_1", MON)
        self.assertEqual(r["status"], "in_review")

    def test_clear_result_approves_without_note_but_consider_needs_assessment(self):
        self.assertEqual(v.approve(reviewed("clear"), "ops", "", MON)["status"], "approved")
        with self.assertRaises(v.VettingError):
            v.approve(reviewed("consider"), "ops", "ok", MON)
        self.assertEqual(v.approve(reviewed("consider"), "ops", NOTE, MON)["status"], "approved")

    def test_unverified_identity_blocks_approval(self):
        r = dict(reviewed("clear"), identity_status="failed")
        with self.assertRaises(v.VettingError):
            v.approve(r, "ops", NOTE, MON)
        self.assertEqual(v.decline_identity(r, "ops", "Selfie did not match", MON)["status"], "denied")

    def test_adverse_action_is_two_steps_with_a_waiting_period(self):
        r = reviewed("consider")
        with self.assertRaises(v.VettingError):
            v.final_adverse(r, "ops", MON)  # no pre-adverse notice yet
        r = v.pre_adverse(r, "ops", "theft_burglary", NOTE, MON)
        self.assertEqual(r["dispute_deadline"][:10], "2026-11-09")  # 5 business days after Monday
        with self.assertRaises(v.VettingError):
            v.pre_adverse(r, "ops", "theft_burglary", NOTE, MON)  # only once
        with self.assertRaises(v.VettingError):
            v.final_adverse(r, "ops", MON + timedelta(days=6))  # Sunday: still inside the wait
        done = v.final_adverse(r, "ops", MON + timedelta(days=7))
        self.assertEqual((done["status"], done["final_adverse_at"][:10]), ("denied", "2026-11-09"))

    def test_a_dispute_pauses_the_final_decision(self):
        r = v.pre_adverse(reviewed("consider"), "ops", "fraud", NOTE, MON)
        r = v.open_dispute(r, MON + timedelta(days=1))
        with self.assertRaises(v.VettingError):
            v.final_adverse(r, "ops", MON + timedelta(days=10))
        r = v.resolve_dispute(r, "ops", MON + timedelta(days=10))
        self.assertEqual(v.final_adverse(r, "ops", MON + timedelta(days=10))["status"], "denied")

    def test_reasons_must_be_written_job_related_and_never_arrest_only(self):
        r = reviewed("consider")
        with self.assertRaises(v.VettingError) as raised:
            v.pre_adverse(r, "ops", "arrest_only", NOTE, MON)
        self.assertIn("Arrests", str(raised.exception))
        for bad_reason, note in (("made_up", NOTE), ("theft_burglary", "too short")):
            with self.subTest(reason=bad_reason), self.assertRaises(v.VettingError):
                v.pre_adverse(r, "ops", bad_reason, note, MON)
        with self.assertRaises(v.VettingError):
            v.pre_adverse(reviewed("clear"), "ops", "theft_burglary", NOTE, MON)  # nothing adverse to act on

    def test_business_days_skip_weekends(self):
        fri = datetime(2026, 11, 6, 12, tzinfo=timezone.utc)
        self.assertEqual(v.add_business_days(fri, 1).date().isoformat(), "2026-11-09")
        self.assertEqual(v.add_business_days(fri, 5).date().isoformat(), "2026-11-13")

    def test_closed_applications_cannot_change(self):
        approved = v.approve(reviewed("clear"), "ops", "", MON)
        with self.assertRaises(v.VettingError):
            v.pre_adverse(dict(approved, background_status="consider"), "ops", "fraud", NOTE, MON)


if __name__ == "__main__":
    unittest.main()
