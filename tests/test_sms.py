"""Text-message reminders, replies, family alerts and the signed Twilio webhook (no network)."""

import contextlib
import io
import os
import pathlib
import tempfile
import threading
import unittest
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime
from unittest import mock

from elder_companion.__main__ import main
from elder_companion.ops import load
from elder_companion.sms import twilio_signature

ROSA, FAMILY = "+14155550123", "+14155550999"
TWILIO = {"TWILIO_ACCOUNT_SID": "AC1", "TWILIO_AUTH_TOKEN": "tok", "TWILIO_FROM": "+14155550000"}
SMTP = {"SMTP_HOST": "smtp.example.com", "SMTP_USER": "care@example.com", "SMTP_PASSWORD": "pw"}


class Outbox:
    """Captures what would be texted (Twilio REST form posts) and emailed (SMTP)."""

    def __init__(self):
        self.texts, self.emails = [], []

    def post(self, url, form, auth):
        f = urllib.parse.parse_qs(form.decode())
        self.texts.append((f["To"][0], f["Body"][0]))

    def smtp(self, outbox):
        class FakeSMTP:
            def __init__(self, host, port, timeout):
                pass

            def __enter__(self):
                return self

            def __exit__(self, *a):
                return False

            def starttls(self):
                pass

            def login(self, user, pw):
                pass

            def send_message(self, msg):
                outbox.emails.append((msg["To"], msg["Subject"], msg.get_content()))

        return FakeSMTP


class SmsTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.store = os.path.join(self.tmp.name, "care.json")
        self.box = Outbox()
        self.env = mock.patch.dict(os.environ, {**TWILIO, **SMTP, "ELDER_COMPANION_WEBHOOK": ""})
        self.env.start()
        self.patches = [
            mock.patch("elder_companion.sms.urllib.request.urlopen", side_effect=AssertionError("no network")),
            mock.patch("elder_companion.sms.smtplib.SMTP", self.box.smtp(self.box)),
        ]
        for p in self.patches:
            p.start()
        real_send = __import__("elder_companion.sms", fromlist=["send_sms"]).send_sms
        self.patches.append(
            mock.patch(
                "elder_companion.sms.send_sms",
                lambda to, body, env=None, post=None: real_send(to, body, env, self.box.post),
            )
        )
        self.patches[-1].start()
        self.c("person-add", "Rosa", "--checkin-deadline", "11:00")
        self.c("med-add", "Rosa", "Lisinopril", "--dose", "10 mg", "--times", "08:00", "--since", "2026-11-01")
        self.c("contact", "Rosa", "--phone", ROSA, "--family-phone", FAMILY, "--family-email", "kid@example.com")

    def tearDown(self):
        for p in reversed(self.patches):
            p.stop()
        self.env.stop()
        self.tmp.cleanup()

    def c(self, *argv):
        out = io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(io.StringIO()):
            code = main([*argv, "--store", self.store])
        return code, out.getvalue()

    def reply(self, text, when):
        from elder_companion.ops import save
        from elder_companion.sms import handle_reply

        people = load(self.store)
        out = handle_reply(people["Rosa"], text, datetime.fromisoformat(when))
        save(people, self.store)
        return out

    def test_a_day_by_text_message(self):
        _, out = self.c("send-due", "Rosa", "--now", "2026-11-18T08:05")
        self.assertIn(f"texted {ROSA}", out)
        self.assertEqual(
            self.box.texts[0], (ROSA, "Time for your medicine: Lisinopril (10 mg). Reply TAKEN when done, or SKIP.")
        )
        self.c("send-due", "Rosa", "--now", "2026-11-18T08:10")
        self.assertEqual(len(self.box.texts), 1)  # never texted twice for the same dose
        self.assertEqual(self.reply("Taken thanks", "2026-11-18T08:12"), "Thank you, noted.")
        log = load(self.store)["Rosa"]
        self.assertEqual(list(log.doses.values()), ["taken"])
        self.c("send-due", "Rosa", "--now", "2026-11-18T09:05")  # two hours before the 11:00 deadline
        self.assertIn("How are you feeling", self.box.texts[-1][1])
        self.assertIn("pain", self.reply("4", "2026-11-18T09:10"))
        self.assertEqual(self.reply("8", "2026-11-18T09:11"), "Thank you! Have a good day.")
        c = load(self.store)["Rosa"].checkins
        day = next(iter(c.values()))
        self.assertEqual((day.mood, day.pain), (4, 8))
        family = [t for t in self.box.texts if t[0] == FAMILY]
        self.assertTrue(any("pain 8/10" in t[1] for t in family))  # high pain reaches the family
        self.assertTrue(any("pain 8/10" in e[2] for e in self.box.emails))

    def test_help_and_misunderstanding(self):
        self.assertIn("told your family", self.reply("HELP I fell", "2026-11-18T15:00"))
        self.assertTrue(any(t[0] == FAMILY and "help" in t[1] for t in self.box.texts))
        self.assertIn("didn't understand", self.reply("banana", "2026-11-18T15:01"))
        self.assertIn("Nothing is waiting", self.reply("yes", "2026-11-18T15:02"))

    def test_missed_checkin_alerts_the_family_once(self):
        self.c("send-due", "Rosa", "--now", "2026-11-18T12:00")
        self.c("send-due", "Rosa", "--now", "2026-11-18T12:30")
        alerts = [t for t in self.box.texts if t[0] == FAMILY]
        self.assertEqual(len(alerts), len({a[1] for a in alerts}))
        self.assertTrue(alerts)

    def test_without_twilio_nothing_is_claimed_as_sent(self):
        with mock.patch.dict(os.environ, {"TWILIO_AUTH_TOKEN": ""}):
            _, out = self.c("send-due", "Rosa", "--now", "2026-11-18T08:05")
        self.assertIn("not texted", out)

    def test_bad_contact_details_are_refused(self):
        self.assertEqual(self.c("contact", "Rosa", "--phone", "555-1234")[0], 1)
        self.assertEqual(self.c("contact", "Rosa", "--family-email", "not-an-email")[0], 1)


class WebhookTests(unittest.TestCase):
    def setUp(self):
        from elder_companion.web import make_server

        self.tmp = tempfile.TemporaryDirectory()
        self.data = pathlib.Path(self.tmp.name)
        self.env = mock.patch.dict(os.environ, {"TWILIO_AUTH_TOKEN": "tok", "PUBLIC_URL": "https://care.example.com"})
        self.env.start()
        store = str(self.data / "elder-companion-care.json")
        for argv in (("person-add", "Rosa"), ("contact", "Rosa", "--phone", ROSA)):
            with contextlib.redirect_stdout(io.StringIO()):
                main([*argv, "--store", store])
        self.srv = make_server("127.0.0.1", 0, self.data, "sk_x")
        threading.Thread(target=self.srv.serve_forever, daemon=True).start()
        self.url = f"http://127.0.0.1:{self.srv.server_address[1]}/twilio/inbound"

    def tearDown(self):
        self.srv.shutdown()
        self.srv.server_close()
        self.env.stop()
        self.tmp.cleanup()

    def post(self, form, sign=True):
        body = urllib.parse.urlencode(form).encode()
        headers = {}
        if sign:
            params = {k: [v] for k, v in form.items()}
            headers["X-Twilio-Signature"] = twilio_signature("tok", "https://care.example.com/twilio/inbound", params)
        req = urllib.request.Request(self.url, data=body, headers=headers)
        try:
            with urllib.request.urlopen(req, timeout=10) as r:
                return r.status, r.read().decode()
        except urllib.error.HTTPError as e:
            with e:
                return e.code, e.read().decode()

    def test_signed_reply_is_answered_and_unsigned_refused(self):
        self.assertEqual(self.post({"From": ROSA, "Body": "help"}, sign=False)[0], 403)
        status, xml = self.post({"From": ROSA, "Body": "what?"})
        self.assertEqual(status, 200)
        self.assertIn("<Message>Sorry, I didn&apos;t understand", xml.replace("'", "&apos;"))
        status, xml = self.post({"From": "+19999999999", "Body": "hi"})
        self.assertIn("not set up", xml)


if __name__ == "__main__":
    unittest.main()
