import argparse
import csv
import os
import sys
from datetime import date, datetime, time, timedelta

from .core import CareLog, CheckIn, Medication, reading_ease, simplify


def demo():
    log = CareLog(
        "Grandpa Joe",
        [Medication("Metformin", "500 mg", [time(8), time(20)]), Medication("Lisinopril", "10 mg", [time(8)])],
    )
    today = date(2026, 10, 24)
    y = today - timedelta(days=1)
    log.record_dose("Metformin", y, time(8))
    log.record_dose("Lisinopril", y, time(8))
    log.record_dose("Lisinopril", today, time(8))
    log.record_checkin(
        CheckIn(today, time(9, 40), mood=3, pain=4, slept_well=False, note="Felt a bit dizzy getting up")
    )
    now = datetime(2026, 10, 24, 12, 0)
    print("Today's reminders:")
    for t, msg in log.reminders(today):
        print(f"  {t:%H:%M} {msg}")
    print()
    print(log.digest(today, now))


def _run(argv=None):
    ap = argparse.ArgumentParser(prog="elder-companion")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("demo")
    s = sub.add_parser("simplify")
    s.add_argument("text")
    a = ap.parse_args(argv)
    if a.cmd == "demo":
        demo()
        return 0
    out = simplify(a.text)
    print(out)
    print(f"\nreading ease {reading_ease(a.text)} -> {reading_ease(out)}")
    return 0


def main(argv=None):
    """Run the CLI; a bad input file or argument exits 2 with a one-line error instead of a traceback.

    Set AGENT_ECONOMY_DEBUG=1 to see the full traceback.
    """
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(errors="replace")
    try:
        return _run(argv)
    except (OSError, ValueError, KeyError, csv.Error) as e:
        if os.environ.get("AGENT_ECONOMY_DEBUG"):
            raise
        msg = e.args[0] if isinstance(e, KeyError) and e.args else e
        print(f"error: {msg}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
