"""Report and block rules that need no server: the text filter and the reason list."""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from marketplace import moderation  # noqa: E402

CLEAN = [
    "Two cats, please use the side door.",
    "Gate code is 4821 and the unit is 12B.",
    "I live at 123 Main St, Silver Spring, MD 20910.",
    "Available 9am-5pm Monday to Friday, call it a day by 4:30.",
    "Bring your own supplies; the kitchen is about 150 sq ft.",
    "2 bedrooms, 1 bathroom, 20910.",
    "Scheduled for 2026-11-14 between 10 and 12.",
    "Thanks! I can do it for $120 on Saturday.",
    "We have a classic hardwood floor and a stubborn stain near the stove.",
    "Please be careful with the grandfather clock.",
    # Normal words in cleaning work must never be blocked.
    "Remove the soap scum in the shower and empty the trash.",
    "Pet piss stains on the carpet, and crap on the patio.",
    "Kill the mold in the basement, please.",
    "",
    None,
]
CONTACT = [
    "Call me at 240-342-6088",
    "my number is (240) 342 6088",
    "text 2403426088 anytime",
    "+1 240.342.6088 works",
    "email me at pat@example.com",
    "pat (at) example.com",
    "visit www.example.com",
    "see https://example.com/me",
    "message me on example.com",
]
ABUSIVE = [
    "you are an idiot",
    "This is SHIT",
    "you stupid moron",
    "what a bitch",
]


class TextFilterTests(unittest.TestCase):
    def test_clean_text_passes(self):
        for text in CLEAN:
            with self.subTest(text=text):
                self.assertIsNone(moderation.check_text(text))

    def test_contact_details_are_rejected(self):
        for text in CONTACT:
            with self.subTest(text=text):
                self.assertEqual(moderation.check_text(text), "contact")

    def test_abusive_words_are_rejected_as_whole_words_only(self):
        for text in ABUSIVE:
            with self.subTest(text=text):
                self.assertEqual(moderation.check_text(text), "abusive")
        # A banned word inside another word is not a match (no "Scunthorpe" problem).
        for text in ("The classic assassin movie", "Please skill-check the cunning plan", "Shooting star decor"):
            with self.subTest(text=text):
                self.assertIsNone(moderation.check_text(text))

    def test_messages_name_the_field_and_never_the_matched_text(self):
        message = moderation.filter_message("contact", "your message")
        self.assertIn("your message", message)
        self.assertNotIn("@", message)

    def test_reasons_are_a_closed_list(self):
        self.assertEqual(moderation.clean_reason("spam"), "spam")
        for bad in ("", None, "rude", "SPAM"):
            with self.subTest(reason=bad):
                with self.assertRaises(moderation.ModerationError):
                    moderation.clean_reason(bad)


if __name__ == "__main__":
    unittest.main()
