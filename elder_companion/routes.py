"""POST /twilio/inbound: texts from the people in care, checked against Twilio's request signature.

Point the Twilio number's "A message comes in" webhook at https://<PUBLIC_URL>/twilio/inbound. Every request
must carry a valid X-Twilio-Signature (HMAC-SHA1 with TWILIO_AUTH_TOKEN over PUBLIC_URL + path and the sorted
form fields); without TWILIO_AUTH_TOKEN and an https PUBLIC_URL the route answers 503 and changes nothing.
The reply (thanks, the next question, or "I didn't understand") goes back in the same TwiML response.
"""

from __future__ import annotations

import hmac
import os
import sys
import threading
from urllib.parse import parse_qs

from .ops import deliver, load, local_now, save
from .sms import find_person, handle_reply, twilio_signature, twiml

STORE_FILE = "elder-companion-care.json"  # the same file the API's commands use
_lock = threading.Lock()


def inbound(handler, body: bytes):
    token = os.environ.get("TWILIO_AUTH_TOKEN", "")
    public = os.environ.get("PUBLIC_URL", "").rstrip("/")
    if not token or not public.startswith("https://"):
        return 503, "text/plain; charset=utf-8", b"Twilio webhooks need TWILIO_AUTH_TOKEN and an https PUBLIC_URL"
    params = parse_qs(body.decode("utf-8", "replace"), keep_blank_values=True)
    expected = twilio_signature(token, public + handler.path, params)
    if not hmac.compare_digest(expected.encode(), handler.headers.get("X-Twilio-Signature", "").encode()):
        return 403, "text/plain; charset=utf-8", b"bad or missing X-Twilio-Signature"
    frm, text = (params.get("From") or [""])[0], (params.get("Body") or [""])[0]
    store = str(handler.data_dir / STORE_FILE)
    with _lock:
        people = load(store)
        name = find_person(people, frm)
        if name is None:
            sys.stderr.write("elder-companion: text from a number not on file\n")
            return 200, "text/xml; charset=utf-8", twiml("This number is not set up yet. Please ask your family.")
        reply = handle_reply(people[name], text, local_now(), webhook=deliver)
        save(people, store)
    return 200, "text/xml; charset=utf-8", twiml(reply)


ROUTES = {"/twilio/inbound": inbound}
