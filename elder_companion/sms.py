"""Reach the person by text message, and the family by text, email or webhook.

Sending uses Twilio's REST API (TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN, TWILIO_FROM) and email uses SMTP
(SMTP_HOST, SMTP_PORT, SMTP_USER, SMTP_PASSWORD, SMTP_FROM). Without them nothing is sent and every result
says so. Replies come back through the signed /twilio/inbound webhook (routes.py) and are understood here:

  TAKEN / YES / DONE   the medicines in the last reminder were taken
  SKIP / NO            they were skipped
  1-5, then 0-10       the daily check-in: mood, then pain
  HELP                 tell the family now

This is a reminder and check-in tool. It is not a medical device and not an emergency service.
"""

from __future__ import annotations

import base64
import os
import re
import smtplib
import urllib.error
import urllib.parse
import urllib.request
from datetime import date, datetime, time, timedelta
from email.message import EmailMessage

from .core import CareLog, CheckIn

YES = {"taken", "take", "took", "yes", "y", "done", "ok", "okay"}
NO = {"skip", "skipped", "no", "n", "missed"}
HELP = {"help", "sos", "emergency"}


def digits(phone: str) -> str:
    return re.sub(r"\D", "", phone or "")


def contact(log: CareLog) -> dict:
    if not hasattr(log, "contact") or not isinstance(log.contact, dict):
        log.contact = {}
    return log.contact


def send_sms(to: str, body: str, env=None, post=None) -> str:
    env = os.environ if env is None else env
    sid, token, frm = env.get("TWILIO_ACCOUNT_SID", ""), env.get("TWILIO_AUTH_TOKEN", ""), env.get("TWILIO_FROM", "")
    if not (sid and token and frm):
        return f"not texted (set TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN, TWILIO_FROM): {body}"
    url = f"https://api.twilio.com/2010-04-01/Accounts/{sid}/Messages.json"
    form = urllib.parse.urlencode({"From": frm, "To": to, "Body": body}).encode()
    auth = base64.b64encode(f"{sid}:{token}".encode()).decode()
    try:
        if post:
            post(url, form, auth)
        else:
            req = urllib.request.Request(url, data=form, headers={"Authorization": f"Basic {auth}"})
            with urllib.request.urlopen(req, timeout=20) as r:
                r.read(2048)
    except urllib.error.HTTPError as e:
        with e:
            return f"NOT TEXTED (Twilio said {e.code}): {e.read()[:200].decode('utf-8', 'replace')}"
    except OSError as e:
        return f"NOT TEXTED ({e})"
    return f"texted {to}"


def send_email(to: str, subject: str, body: str, env=None, smtp=None) -> str:
    env = os.environ if env is None else env
    host = env.get("SMTP_HOST", "")
    if not host:
        return "not emailed: set SMTP_HOST (and SMTP_USER, SMTP_PASSWORD, SMTP_FROM)"
    msg = EmailMessage()
    msg["From"] = env.get("SMTP_FROM") or env.get("SMTP_USER", "")
    msg["To"], msg["Subject"] = to, subject
    msg.set_content(body)
    try:
        with (smtp or smtplib.SMTP)(host, int(env.get("SMTP_PORT", "587")), timeout=20) as s:
            s.starttls()
            if env.get("SMTP_USER"):
                s.login(env["SMTP_USER"], env.get("SMTP_PASSWORD", ""))
            s.send_message(msg)
    except (OSError, smtplib.SMTPException) as e:
        return f"NOT EMAILED ({e})"
    return f"emailed {to}"


def tell_family(log: CareLog, text: str, env=None, post=None, smtp=None, webhook=None) -> list[str]:
    """Every channel the family has: their phone, their email, and the webhook. Returns one status per channel."""
    c = contact(log)
    out = []
    if c.get("family_phone"):
        out.append(send_sms(c["family_phone"], text[:1500], env, post))
    if c.get("family_email"):
        out.append(send_email(c["family_email"], f"Update about {log.person}", text, env, smtp))
    if webhook:
        out.append(webhook(text))
    if not out:
        out.append("not sent: add a family phone or email with `contact`, or set ELDER_COMPANION_WEBHOOK")
    return out


def due(log: CareLog, now: datetime, window_min: int = 20) -> list[tuple[str, time]]:
    """Doses scheduled in the last `window_min` minutes that were neither recorded nor already texted."""
    sent = set(contact(log).get("sent", []))
    out = []
    for m in log.meds:
        if m.since and m.since > now.date():
            continue
        for t in m.times:
            at = datetime.combine(now.date(), t)
            key = f"{m.name}|{now.date().isoformat()}|{t:%H:%M}"
            recorded = (m.name, now.date(), t) in log.doses
            if now - timedelta(minutes=window_min) <= at <= now and key not in sent and not recorded:
                out.append((m.name, t))
    return out


def send_due(
    log: CareLog, now: datetime, env=None, post=None, smtp=None, webhook=None, window_min: int = 20
) -> list[str]:
    """One tick of the schedule: reminders due, the morning check-in question, and new family alerts."""
    c = contact(log)
    lines = []
    phone = c.get("phone")
    doses = due(log, now, window_min)
    if doses:
        meds = {m.name: m for m in log.meds}
        what = "; ".join(f"{name} ({meds[name].dose})" for name, _ in doses)
        text = f"Time for your medicine: {what}. Reply TAKEN when done, or SKIP."
        lines.append(send_sms(phone, text, env, post) if phone else "not texted: add the person's phone with `contact`")
        c.setdefault("sent", []).extend(f"{n}|{now.date().isoformat()}|{t:%H:%M}" for n, t in doses)
        c["pending"] = {"kind": "dose", "doses": [[n, now.date().isoformat(), f"{t:%H:%M}"] for n, t in doses]}
    ask_at = (datetime.combine(now.date(), log.checkin_deadline) - timedelta(hours=2)).time()
    if phone and now.time() >= ask_at and now.date() not in log.checkins and c.get("asked") != now.date().isoformat():
        lines.append(send_sms(phone, "Good morning! How are you feeling today? Reply 1 (bad) to 5 (great).", env, post))
        c["asked"] = now.date().isoformat()
        if not doses:
            c["pending"] = {"kind": "mood"}
    told = set(c.get("told", []))
    for alert in log.escalations(now.date(), now):
        key = f"{now.date().isoformat()}|{alert}"
        if key not in told:
            lines += tell_family(log, alert, env, post, smtp, webhook)
            told.add(key)
    week_ago = (now.date() - timedelta(days=7)).isoformat()
    c["told"] = sorted(k for k in told if k[:10] >= week_ago)
    c["sent"] = [k for k in c.get("sent", []) if k.split("|")[1] >= week_ago]
    return lines or ["nothing due"]


def handle_reply(log: CareLog, body: str, now: datetime, env=None, post=None, smtp=None, webhook=None) -> str:
    """Understand a text from the person; returns the reply to send back."""
    c = contact(log)
    words = re.findall(r"[a-z]+|\d+", body.lower())
    word = words[0] if words else ""
    pending = c.get("pending") or {}
    if word in HELP:
        tell_family(log, f"{log.person} texted for help at {now:%H:%M}: {body.strip()[:300]}", env, post, smtp, webhook)
        return "I've told your family. If this is an emergency, call your local emergency number now."
    if pending.get("kind") == "dose" and (word in YES or word in NO):
        for name, day, at in pending["doses"]:
            log.record_dose(name, date.fromisoformat(day), time.fromisoformat(at), word in YES)
        c["pending"] = (
            {"kind": "mood"} if c.get("asked") == now.date().isoformat() and now.date() not in log.checkins else {}
        )
        return "Thank you, noted." if word in YES else "Okay, noted as skipped. Your family can see this."
    if word.isdigit() and pending.get("kind") == "mood" and 1 <= int(word) <= 5:
        c["pending"] = {"kind": "pain", "mood": int(word)}
        return "Thank you. Any pain today? Reply 0 (none) to 10 (worst)."
    if word.isdigit() and pending.get("kind") == "pain" and 0 <= int(word) <= 10:
        log.record_checkin(
            CheckIn(
                now.date(),
                now.time().replace(second=0, microsecond=0),
                pending["mood"],
                int(word),
                True,
                True,
                "by text message (sleep and meals not asked)",
            )
        )
        c["pending"] = {}
        for alert in log.escalations(now.date(), now):
            tell_family(log, alert, env, post, smtp, webhook)
        return "Thank you! Have a good day."
    if word in YES or word in NO:
        return "Thanks! Nothing is waiting for an answer right now."
    hint = {"mood": "a number from 1 to 5", "pain": "a number from 0 to 10", "dose": "TAKEN or SKIP"}.get(
        pending.get("kind", ""), "TAKEN, SKIP or HELP"
    )
    return f"Sorry, I didn't understand. Please reply {hint}."


def twilio_signature(token: str, url: str, params: dict[str, list[str]]) -> str:
    import hashlib
    import hmac

    data = url + "".join(k + v for k in sorted(params) for v in sorted(params[k]))
    return base64.b64encode(hmac.new(token.encode(), data.encode("utf-8"), hashlib.sha1).digest()).decode()


def find_person(people: dict, phone: str):
    want = digits(phone)
    for name, log in people.items():
        if want and digits(contact(log).get("phone", "")) == want:
            return name
    return None


def twiml(text: str) -> bytes:
    from xml.sax.saxutils import escape

    return f'<?xml version="1.0" encoding="UTF-8"?><Response><Message>{escape(text)}</Message></Response>'.encode()


__all__ = ["send_due", "handle_reply", "send_sms", "send_email", "tell_family", "twilio_signature"]
