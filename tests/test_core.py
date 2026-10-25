import unittest
from datetime import date, datetime, time, timedelta

from elder_companion import CareLog, CheckIn, Medication, reading_ease, simplify

D = date(2026, 10, 24)


class Tests(unittest.TestCase):
    def setUp(self):
        self.log = CareLog("Joe", [Medication("Metformin", "500 mg", [time(8), time(20)])])

    def test_two_missed_doses_escalate(self):
        now = datetime(2026, 10, 24, 11)
        self.log.record_dose("Metformin", D - timedelta(days=1), time(8))
        alerts = self.log.escalations(D, now)  # yesterday 20:00 missed + today 08:00 missed
        self.assertTrue(any("missed two doses" in a for a in alerts))

    def test_adherence(self):
        now = datetime(2026, 10, 24, 23)
        self.log.record_dose("Metformin", D, time(8))
        self.assertEqual(self.log.adherence(D, D, now)["Metformin"], 0.5)

    def test_checkin_alerts(self):
        now = datetime(2026, 10, 24, 12)
        self.assertTrue(any("No check-in" in a for a in self.log.escalations(D, now)))
        self.log.record_checkin(CheckIn(D, time(9), 3, 8, note="I fell in the kitchen"))
        alerts = self.log.escalations(D, now)
        self.assertTrue(any("pain 8/10" in a for a in alerts))
        self.assertTrue(any("fell" in a for a in alerts))

    def test_low_mood_streak(self):
        for i in range(3):
            self.log.record_checkin(CheckIn(D - timedelta(days=i), time(9), 2, 0))
        self.assertTrue(any("mood has been low" in a for a in self.log.escalations(D, datetime(2026, 10, 24, 9, 30))))

    def test_digest(self):
        self.log.record_checkin(CheckIn(D, time(9), 4, 1))
        text = self.log.digest(D, datetime(2026, 10, 24, 9, 30))
        self.assertIn("Mood: good", text)

    def test_simplify(self):
        src = (
            "Please authenticate via the portal in order to reschedule your appointment with the physician, "
            "subsequently you will receive a notification confirming the additional details of your visit."
        )
        out = simplify(src)
        self.assertIn("sign in", out)
        self.assertIn("doctor", out)
        self.assertNotIn("subsequently", out.lower())
        self.assertGreater(reading_ease(out), reading_ease(src))

    def test_red_flags_survive_phone_punctuation_and_cover_emergencies(self):
        now = datetime(2026, 10, 24, 10, 0)
        for note in ("I can\u2019t breathe well", "I fell and I can't get up", "please call 911", "my chest hurts"):
            with self.subTest(note=note):
                log = CareLog("Joe")
                log.record_checkin(CheckIn(D, time(9), 3, 2, note=note))
                self.assertTrue(any("said" in a for a in log.escalations(D, now)), note)

    def test_checkin_values_are_validated(self):
        for mood, pain in ((0, 2), (6, 2), (3, 11), (3, -1)):
            with self.subTest(mood=mood, pain=pain), self.assertRaises(ValueError):
                self.log.record_checkin(CheckIn(D, time(9), mood, pain))

    def test_missed_in_a_row_uses_real_dose_order(self):
        log = CareLog("Joe", [Medication("Metformin", "500 mg", [time(20), time(8)])])
        log.record_dose("Metformin", D - timedelta(days=1), time(8), taken=True)
        log.record_dose("Metformin", D - timedelta(days=1), time(20), taken=False)  # missed last night...
        log.record_dose("Metformin", D, time(8), taken=False)  # ...and this morning: two in a row
        log.record_dose("Metformin", D, time(20), taken=True)
        alerts = log.escalations(D, datetime(2026, 10, 24, 23, 0))
        self.assertTrue(any("in a row" in a for a in alerts), alerts)


if __name__ == "__main__":
    unittest.main()
