"""Care engine: medication reminders, adherence, check-ins, escalations, digest, plain-language rewriting."""

from __future__ import annotations

import itertools
import re
from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta

__all__ = ["Medication", "CheckIn", "CareLog", "simplify", "reading_ease"]

RED_FLAGS = [
    "fell",
    "fall",
    "dizzy",
    "chest pain",
    "can't breathe",
    "cannot breathe",
    "confused",
    "bleeding",
    "lost",
    "scared",
]
JARGON = {
    "authenticate": "sign in",
    "subsequently": "then",
    "utilize": "use",
    "approximately": "about",
    "reschedule": "change the time of",
    "portal": "website",
    "commence": "start",
    "terminate": "end",
    "prior to": "before",
    "in order to": "to",
    "assistance": "help",
    "medication": "medicine",
    "physician": "doctor",
    "notification": "message",
    "insufficient": "not enough",
    "purchase": "buy",
    "however": "but",
    "additional": "more",
    "residence": "home",
    "facilitate": "help",
}


@dataclass
class Medication:
    name: str
    dose: str
    times: list  # list[time]


@dataclass
class CheckIn:
    day: date
    at: time
    mood: int
    pain: int
    slept_well: bool = True
    ate: bool = True
    note: str = ""


@dataclass
class CareLog:
    person: str
    meds: list = field(default_factory=list)
    doses: dict = field(default_factory=dict)  # (med, day, time) -> "taken"/"skipped"
    checkins: dict = field(default_factory=dict)  # day -> CheckIn
    checkin_deadline: time = time(11, 0)

    def reminders(self, day: date) -> list[tuple[time, str]]:
        return sorted((t, f"Time for your {m.name} ({m.dose})") for m in self.meds for t in m.times)

    def record_dose(self, med: str, day: date, at: time, taken: bool = True):
        self.doses[(med, day, at)] = "taken" if taken else "skipped"

    def record_checkin(self, c: CheckIn):
        self.checkins[c.day] = c

    def _status(self, med: Medication, day: date, t: time, now: datetime) -> str:
        s = self.doses.get((med.name, day, t))
        if s:
            return s
        due = datetime.combine(day, t)
        return "missed" if now > due + timedelta(hours=2) else "pending"

    def adherence(self, start: date, end: date, now: datetime) -> dict:
        out = {}
        for m in self.meds:
            taken = due = 0
            d = start
            while d <= end:
                for t in m.times:
                    st = self._status(m, d, t, now)
                    if st == "pending":
                        continue
                    due += 1
                    taken += st == "taken"
                d += timedelta(days=1)
            out[m.name] = round(taken / due, 3) if due else None
        return out

    def escalations(self, day: date, now: datetime) -> list[str]:
        alerts = []
        for m in self.meds:
            slots = [(d, t) for d in (day - timedelta(days=1), day) for t in m.times]
            statuses = [self._status(m, d, t, now) for d, t in slots]
            statuses = [s for s in statuses if s != "pending"]
            for a, b in itertools.pairwise(statuses):
                if a in ("missed", "skipped") and b in ("missed", "skipped"):
                    alerts.append(f"{self.person} missed two doses in a row of {m.name}")
                    break
        c = self.checkins.get(day)
        if not c and now.time() > self.checkin_deadline and now.date() == day:
            alerts.append(f"No check-in from {self.person} by {self.checkin_deadline:%H:%M}")
        if c:
            if c.pain >= 7:
                alerts.append(f"{self.person} reported pain {c.pain}/10")
            low = c.note.lower()
            flags = [w for w in RED_FLAGS if w in low]
            if flags:
                alerts.append(f'{self.person} said: "{c.note}" (mentions {", ".join(flags)})')
        moods = [self.checkins.get(day - timedelta(days=i)) for i in range(3)]
        if all(m and m.mood <= 2 for m in moods):
            alerts.append(f"{self.person}'s mood has been low for 3 days")
        return alerts

    def digest(self, day: date, now: datetime) -> str:
        c = self.checkins.get(day)
        adh = self.adherence(day, day, now)
        lines = [f"Daily update for {self.person} - {day:%A %d %B}"]
        if c:
            mood_word = {1: "very low", 2: "low", 3: "okay", 4: "good", 5: "great"}[c.mood]
            lines.append(
                f"Checked in at {c.at:%H:%M}. Mood: {mood_word}. Pain: {c.pain}/10. "
                f"{'Slept well' if c.slept_well else 'Slept poorly'}, {'has eaten' if c.ate else 'has not eaten yet'}."
            )
            if c.note:
                lines.append(f'They said: "{c.note}"')
        else:
            lines.append("No check-in yet today.")
        for med, rate in adh.items():
            if rate is not None:
                lines.append(f"{med}: {round(rate * 100)}% of today's doses taken.")
        alerts = self.escalations(day, now)
        lines.append("Needs attention: " + "; ".join(alerts) if alerts else "Nothing needs your attention today.")
        return "\n".join(lines)


def _syllables(word: str) -> int:
    w = word.lower().strip(".,!?;:")
    groups = re.findall(r"[aeiouy]+", w)
    n = len(groups) - (1 if w.endswith("e") and len(groups) > 1 else 0)
    return max(1, n)


def reading_ease(text: str) -> float:
    sentences = max(1, len(re.findall(r"[.!?]+", text)) or 1)
    words = re.findall(r"[A-Za-z']+", text)
    if not words:
        return 100.0
    syl = sum(_syllables(w) for w in words)
    return round(206.835 - 1.015 * len(words) / sentences - 84.6 * syl / len(words), 1)


def simplify(text: str, max_words: int = 14) -> str:
    out = text
    for hard, easy in sorted(JARGON.items(), key=lambda kv: -len(kv[0])):
        out = re.sub(rf"\b{re.escape(hard)}\b", easy, out, flags=re.I)
    sentences = re.split(r"(?<=[.!?])\s+", out.strip())
    result = []
    for s in sentences:
        words = s.split()
        while len(words) > max_words:
            cut = next((i for i in range(max_words, 3, -1) if words[i - 1].endswith(",")), max_words)
            chunk = " ".join(words[:cut]).rstrip(",;")
            result.append(chunk[0].upper() + chunk[1:] + ".")
            words = words[cut:]
        if words:
            chunk = " ".join(words)
            chunk = chunk[0].upper() + chunk[1:]
            result.append(chunk if chunk[-1] in ".!?" else chunk + ".")
    return " ".join(result)
