import argparse
import contextlib
import io
import os
import tempfile
import unittest

from elder_companion.__main__ import build_parser
from elder_companion.ops import deliver, load, run_ops

DAY = "2026-12-01"


class CareOpsTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = os.path.join(self.tmp.name, "care.json")
        self.posted = []
        self.ok("person-add", "Rose")
        self.ok("med-add", "Rose", "Lisinopril", "--dose", "10 mg", "--times", "08:00", "20:00", "--since", DAY)

    def tearDown(self):
        self.tmp.cleanup()

    def run_cmd(self, *argv, env=None):
        a: argparse.Namespace = build_parser().parse_args([*argv, "--store", self.path])
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            code = run_ops(a, env=env or {}, post=lambda url, body: self.posted.append((url, body)))
        return code, out.getvalue()

    def ok(self, *argv):
        code, out = self.run_cmd(*argv)
        self.assertEqual(code, 0, out)
        return out

    def test_a_new_prescription_does_not_raise_a_false_missed_dose_alarm(self):
        self.ok("checkin", "Rose", "--mood", "4", "--pain", "1", "--now", f"{DAY}T09:00")
        self.assertEqual(
            self.run_cmd("alerts", "Rose", "--now", f"{DAY}T09:30"), (0, "Nothing needs attention for Rose.\n")
        )

    def test_two_missed_doses_a_fall_and_high_pain_reach_the_family(self):
        self.ok(
            "checkin", "Rose", "--mood", "2", "--pain", "8", "--note", "I fell in the kitchen", "--now", f"{DAY}T09:00"
        )
        env = {"ELDER_COMPANION_WEBHOOK": "https://hooks.example.com/family"}
        code, out = self.run_cmd("alerts", "Rose", "--now", "2026-12-01T23:30", "--send", env=env)
        self.assertEqual(code, 1)
        for needle in ("missed two doses in a row", "pain 8/10", "mentions fell", "sent to the family"):
            self.assertIn(needle, out)
        self.assertEqual(self.posted[0][0], "https://hooks.example.com/family")

    def test_taken_doses_show_in_the_digest_and_survive_a_restart(self):
        self.ok("dose", "Rose", "Lisinopril", "--at", "08:00", "--day", DAY)
        self.ok("checkin", "Rose", "--mood", "4", "--pain", "1", "--now", f"{DAY}T09:00")
        digest = self.ok("digest", "Rose", "--now", f"{DAY}T12:00")
        self.assertIn("100% of today's doses taken", digest)
        self.assertIn("Nothing needs your attention", digest)
        self.assertEqual(len(load(self.path)["Rose"].doses), 1)

    def test_delivery_failures_are_loud_and_unconfigured_is_explicit(self):
        def broken(url, body):
            raise OSError("timeout")

        env = {"ELDER_COMPANION_WEBHOOK": "https://hooks.example.com/family"}
        self.assertIn("NOT DELIVERED", deliver("x", env, broken))
        self.assertIn("not sent", deliver("x", {}))
        self.assertIn("must be an https", deliver("x", {"ELDER_COMPANION_WEBHOOK": "http://insecure"}))

    def test_refusals(self):
        for argv in (
            ["person-add", "Rose"],
            ["med-add", "Rose", "Lisinopril", "--dose", "x", "--times", "08:00"],
            ["med-add", "Rose", "Aspirin", "--dose", "x", "--times", "8am"],
            ["dose", "Rose", "Lisinopril", "--at", "09:00"],  # not a scheduled time
            ["dose", "Rose", "Unknown", "--at", "08:00"],
            ["checkin", "Rose", "--mood", "9", "--pain", "1"],
            ["reminders", "Nobody"],
        ):
            with self.subTest(argv=argv):
                self.assertEqual(self.run_cmd(*argv)[0], 1)


if __name__ == "__main__":
    unittest.main()
