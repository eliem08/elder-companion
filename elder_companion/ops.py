"""Operating commands: a persistent care log per person (also served by the web app).

Set ELDER_COMPANION_WEBHOOK to an https Slack/Discord/any webhook and `alerts --send` / `digest --send`
deliver to the family as well as printing. The URL is operator configuration, never a request parameter.
This is a reminder and check-in tool, not a medical device and not an emergency service.
"""

import json
import os
import urllib.request
from datetime import date, datetime, time, timedelta

from .core import CareLog, CheckIn, Medication

OPS = ("person-add", "med-add", "reminders", "dose", "checkin", "alerts", "digest", "adherence")


class CareError(ValueError):
    pass


def _time(text: str) -> time:
    try:
        return time.fromisoformat(text)
    except ValueError:
        raise CareError(f"{text!r} is not a time like 08:00") from None


def _now(text) -> datetime:
    if not text:
        return datetime.now()
    try:
        return datetime.fromisoformat(text)
    except ValueError:
        raise CareError(f"{text!r} is not a date-time like 2026-12-01T12:00") from None


def load(path: str) -> dict[str, CareLog]:
    try:
        with open(path, encoding="utf-8-sig") as fh:
            doc = json.load(fh)
    except FileNotFoundError:
        return {}
    if not isinstance(doc, dict) or not isinstance(doc.get("people"), dict):
        raise CareError(f"{path}: not an elder-companion store")
    people = {}
    for name, p in doc["people"].items():
        log = CareLog(name, checkin_deadline=time.fromisoformat(p["checkin_deadline"]))
        log.meds = [
            Medication(
                m["name"],
                m["dose"],
                [time.fromisoformat(t) for t in m["times"]],
                date.fromisoformat(m["since"]) if m.get("since") else None,
            )
            for m in p["meds"]
        ]
        for med, day, at, status in p["doses"]:
            log.doses[(med, date.fromisoformat(day), time.fromisoformat(at))] = status
        for c in p["checkins"]:
            day = date.fromisoformat(c.pop("day"))
            log.checkins[day] = CheckIn(day, time.fromisoformat(c.pop("at")), **c)
        people[name] = log
    return people


def save(people: dict[str, CareLog], path: str):
    doc = {"people": {}}
    for name, log in people.items():
        doc["people"][name] = {
            "checkin_deadline": log.checkin_deadline.isoformat("minutes"),
            "meds": [
                {
                    "name": m.name,
                    "dose": m.dose,
                    "times": [t.isoformat("minutes") for t in m.times],
                    "since": m.since.isoformat() if m.since else None,
                }
                for m in log.meds
            ],
            "doses": [[med, d.isoformat(), t.isoformat("minutes"), s] for (med, d, t), s in log.doses.items()],
            "checkins": [
                {**c.__dict__, "day": c.day.isoformat(), "at": c.at.isoformat("minutes")} for c in log.checkins.values()
            ],
        }
    tmp = f"{path}.tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(doc, fh, indent=2)
    os.replace(tmp, path)


def deliver(text: str, env=None, post=None) -> str:
    """Send to the family webhook if one is configured. Returns a short status line."""
    url = (os.environ if env is None else env).get("ELDER_COMPANION_WEBHOOK", "")
    if not url:
        return "not sent: set ELDER_COMPANION_WEBHOOK to deliver to the family"
    if not url.startswith("https://"):
        return "not sent: ELDER_COMPANION_WEBHOOK must be an https:// URL"
    body = json.dumps({"text": text, "content": text[:2000]}).encode()
    try:
        if post:
            post(url, body)
        else:
            req = urllib.request.Request(url, data=body, headers={"Content-Type": "application/json"})
            with urllib.request.urlopen(req, timeout=10) as r:
                r.read(1024)
    except OSError as e:
        return f"NOT DELIVERED ({e}): contact the family another way"
    return "sent to the family"


def add_ops(sub):
    store = os.environ.get("ELDER_COMPANION_STORE", "care.json")
    p = sub.add_parser("person-add", help="start a care log for someone")
    p.add_argument("person")
    p.add_argument("--checkin-deadline", default="11:00", help="alert the family if no check-in by this time")
    p = sub.add_parser("med-add", help="add a medicine and when it is taken")
    p.add_argument("person")
    p.add_argument("medicine")
    p.add_argument("--dose", required=True, help="as written on the label, e.g. '10 mg'")
    p.add_argument("--times", nargs="+", required=True, help="e.g. 08:00 20:00")
    p.add_argument("--since", help="first day of the prescription, default today")
    sub.add_parser("reminders", help="today's reminders in plain words").add_argument("person")
    p = sub.add_parser("dose", help="record a dose as taken (or skipped)")
    p.add_argument("person")
    p.add_argument("medicine")
    p.add_argument("--at", required=True, help="the scheduled time, e.g. 08:00")
    p.add_argument("--skipped", action="store_true")
    p.add_argument("--day", help="YYYY-MM-DD, default today")
    p = sub.add_parser("checkin", help="record the daily check-in")
    p.add_argument("person")
    p.add_argument("--mood", type=int, required=True, help="1 (very low) to 5 (great)")
    p.add_argument("--pain", type=int, required=True, help="0 to 10")
    p.add_argument("--slept-poorly", action="store_true")
    p.add_argument("--not-eaten", action="store_true")
    p.add_argument("--note", default="", help="anything they said")
    p.add_argument("--now", help=argparse_now_help())
    for name in ("alerts", "digest"):
        p = sub.add_parser(
            name, help=f"{'what needs the family now' if name == 'alerts' else 'the daily family update'}"
        )
        p.add_argument("person")
        p.add_argument("--send", action="store_true", help="also deliver to the family webhook")
        p.add_argument("--now", help=argparse_now_help())
    p = sub.add_parser("adherence", help="share of doses taken over recent days")
    p.add_argument("person")
    p.add_argument("--days", type=int, default=7)
    for name in OPS:
        sub.choices[name].add_argument("--store", default=store)


def argparse_now_help() -> str:
    return "act as of this date-time (default: now), e.g. 2026-12-01T12:00"


def run_ops(a, env=None, post=None) -> int:
    try:
        people = load(a.store)
        if a.cmd != "person-add" and a.person not in people:
            raise CareError(f"no care log for {a.person!r}; run person-add first")
        code = _run(people, a, env, post)
        save(people, a.store)
        return code
    except ValueError as e:
        print(f"refused: {e}")
        return 1


def _run(people, a, env, post) -> int:
    c = a.cmd
    if c == "person-add":
        if a.person in people:
            raise CareError(f"{a.person} already has a care log")
        people[a.person] = CareLog(a.person, checkin_deadline=_time(a.checkin_deadline))
        print(f"care log started for {a.person}; check-in expected by {a.checkin_deadline}")
        return 0
    log: CareLog = people[a.person]
    if c == "med-add":
        if any(m.name == a.medicine for m in log.meds):
            raise CareError(f"{a.medicine} is already on {a.person}'s list")
        since = date.fromisoformat(a.since) if a.since else date.today()
        log.meds.append(Medication(a.medicine, a.dose, sorted(_time(t) for t in a.times), since))
        print(f"{a.medicine} ({a.dose}) at {', '.join(a.times)}")
    elif c == "reminders":
        rows = log.reminders(date.today())
        for t, text in rows:
            print(f"{t:%H:%M}  {text}")
        if not rows:
            print("no medicines on the list yet")
    elif c == "dose":
        med = next((m for m in log.meds if m.name == a.medicine), None)
        at = _time(a.at)
        if not med:
            raise CareError(f"{a.medicine} is not on {a.person}'s list")
        if at not in med.times:
            raise CareError(f"{a.medicine} is scheduled at {', '.join(f'{t:%H:%M}' for t in med.times)}, not {a.at}")
        day = date.fromisoformat(a.day) if a.day else date.today()
        log.record_dose(a.medicine, day, at, not a.skipped)
        print(f"{a.medicine} {a.at} on {day}: {'skipped' if a.skipped else 'taken'}")
    elif c == "checkin":
        now = _now(a.now)
        log.record_checkin(
            CheckIn(
                now.date(),
                now.time().replace(second=0, microsecond=0),
                a.mood,
                a.pain,
                not a.slept_poorly,
                not a.not_eaten,
                a.note,
            )
        )
        alerts = log.escalations(now.date(), now)
        print("check-in recorded" + (f"; {len(alerts)} alert(s): run alerts" if alerts else ""))
    elif c in ("alerts", "digest"):
        now = _now(a.now)
        if c == "alerts":
            alerts = log.escalations(now.date(), now)
            text = "\n".join(alerts) if alerts else f"Nothing needs attention for {a.person}."
        else:
            alerts, text = True, log.digest(now.date(), now)
        print(text)
        if a.send and alerts:
            print(deliver(text, env, post))
        return 1 if c == "alerts" and alerts else 0
    else:
        if a.days < 1:
            raise CareError("days must be at least 1")
        now = datetime.now()
        rates = log.adherence(now.date() - timedelta(days=a.days - 1), now.date(), now)
        for med, rate in rates.items():
            print(f"{med:<20}{'no doses due yet' if rate is None else f'{rate:.0%} taken'}")
        if not rates:
            print("no medicines on the list yet")
    return 0
