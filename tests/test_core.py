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
        src = ("Please authenticate via the portal in order to reschedule your appointment with the physician, "
               "subsequently you will receive a notification confirming the additional details of your visit.")
        out = simplify(src)
        self.assertIn("sign in", out)
        self.assertIn("doctor", out)
        self.assertNotIn("subsequently", out.lower())
        self.assertGreater(reading_ease(out), reading_ease(src))


if __name__ == "__main__":
    unittest.main()
