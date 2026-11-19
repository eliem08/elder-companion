<!-- sell-kit:start -->
# Elder Companion

[![CI](https://github.com/eliem08/elder-companion/actions/workflows/ci.yml/badge.svg)](https://github.com/eliem08/elder-companion/actions/workflows/ci.yml)

> **Medicine reminders and daily check-ins for older adults, with alerts that keep the family in the loop.**

**Who it's for:** Adult children caring for a parent who lives alone, and home-care agencies.

**The problem:** Missed medication, falls and loneliness go unnoticed until a crisis, and families can't check in every hour.

**What you get:** Medication reminders and daily check-ins by text message with simple replies, adherence tracking, red-flag alerts to family by text, email and webhook, and plain-language rewriting of confusing messages.

## Quickstart

Customers receive a release archive with the wheel and the examples. Python 3.10+ and no other dependencies.

```bash
pip install elder_companion-0.1.0-py3-none-any.whl
elder-companion person-add Rose --store care.json
elder-companion med-add Rose Lisinopril --dose "10 mg" --times 08:00 20:00 --store care.json
elder-companion contact Rose --phone +14155550123 --family-email kid@example.com --store care.json
```

## Web app and API

Every command is also a JSON API endpoint and a browser form, served by the built-in web app.

```bash
elder-companion-web --port 8000          # then open http://127.0.0.1:8000
elder-companion-web keys create --label "first customer"   # prints an API key (stored hashed)
docker build -t elder-companion . && docker run -p 8000:8000 -e API_KEYS=sk_... -v elder-companion-data:/data elder-companion
```

Every API call needs `Authorization: Bearer <key>` once any key exists; a server on a public address refuses to start without one. Calls are rate-limited per key (60/min, `--rate`) and metered: `elder-companion-web usage` prints calls per key for billing.

Endpoints: `POST /api/demo`, `POST /api/simplify`, `POST /api/person-add`, `POST /api/contact`, `POST /api/send-due`, `POST /api/med-add`, `POST /api/reminders`, `POST /api/dose`, `POST /api/checkin`, `POST /api/alerts`, `POST /api/digest`, `POST /api/adherence`, plus `GET /healthz` and `GET /api/spec` (machine-readable field list).
Files are sent as `{"name": ..., "content": ...}`, folders as `{"files": [...]}` or a base64 zip.

## Deploy and sell

[![Deploy to Render](https://render.com/images/deploy-to-render-button.svg)](https://render.com/deploy?repo=https://github.com/eliem08/elder-companion)

`render.yaml` (one click, above) and `fly.toml` (`fly launch --copy-config`) both run the Dockerfile with a persistent `/data` volume and a `/healthz` check.
To sell self-serve, set four variables and point a Stripe webhook at `https://<your-host>/billing/webhook` (events `checkout.session.completed` and `customer.subscription.deleted`):

| Variable | Example |
|---|---|
| `STRIPE_SECRET_KEY` | `sk_live_...` |
| `STRIPE_WEBHOOK_SECRET` | `whsec_...` |
| `STRIPE_PRICES` | `team=price_123,business=price_456` |
| `PUBLIC_URL` | `https://elder-companion.example.com` |
| `PLAN_QUOTAS` (optional) | `team=10000,business=250000` successful calls per key per month |

Buyers pick a plan on `/pricing`, pay on Stripe Checkout and see their API key once on the success page. Cancelling the subscription revokes the key. A selling server always requires a key.

## Pricing

Monthly plans start with a 14-day free trial. Prices in USD, billed monthly unless noted.

| Plan | Price | Includes |
|---|---|---|
| **Family** | $19 per month | 1 loved one; Reminders and check-ins; Daily family digest |
| **Family Plus** | $39 per month | 2 loved ones; Reminders and check-ins by text message; Red-flag alerts by text, email and webhook; Dose adherence report |
| **Care Agency** | $9 per client per month | Multiple clients in one store; Priority support |

To start a trial or buy a plan, [request access](https://github.com/eliem08/elder-companion/issues/new?title=Elder%20Companion%20trial&labels=sales).

Plan note: every plan runs the same software, and every API key unlocks all of it. Monthly call volumes are
enforced when `PLAN_QUOTAS` is set (see Deploy and sell); seat and agent limits are licence terms the code does
not enforce. Support, SLA and done-for-you items are services.

## Licence

Proprietary. Copyright (c) 2026 eliem08. All rights reserved. Use requires a paid plan or an active trial; see [LICENSE](LICENSE).
<!-- sell-kit:end -->

## What it does

- **Medication schedule** → today's reminders; record taken / skipped
- **Adherence** per medication over N days
- **Daily check-in** (mood 1–5, pain 0–10, slept well?, ate?, free text)
- **Escalation rules** → family alerts:
  - two consecutive missed doses of the same medication
  - no check-in by the deadline (e.g. 11:00)
  - mood ≤ 2 for 3 days running, or pain ≥ 7
  - worrying words in free text ("fell", "dizzy", "chest pain", "can't breathe")
- **Family digest**: one plain-English daily summary for adult children
- **By text message**: the person gets their reminders and the morning check-in as texts, and answers
  with TAKEN, SKIP, a number, or HELP. The family gets alerts by text, email and webhook (see below).
- **Plain-language rewriter** for anything the companion reads aloud:
  jargon → everyday words, long sentences split, Flesch reading-ease score

## Quickstart

```bash
pip install -e .
elder-companion demo
elder-companion simplify "Please authenticate via the portal to reschedule your appointment, subsequently..."
```

## Reaching the person and the family

```bash
elder-companion contact Rosa --phone +14155550123 --family-phone +14155550999 --family-email kid@example.com
elder-companion send-due Rosa      # run every 5-10 minutes from cron, a scheduler, or POST /api/send-due
```

- **Each `send-due` run:**
  - texts any medicine that came due in the last 20 minutes (each dose once) and asks for TAKEN or SKIP;
  - asks "How are you feeling, 1 to 5?" two hours before the check-in deadline, then asks about pain from 0 to
    10;
  - sends each new red-flag alert (missed doses, no check-in, low mood, high pain, worrying words) to the
    family once, by text, email and webhook.
- **Replies:**
  - They come back to `POST /twilio/inbound` on the hosted server. Set the Twilio number's "A message comes
    in" webhook to `https://<your-host>/twilio/inbound`.
  - Every request must carry Twilio's signature (HMAC with your auth token), or it is refused.
  - Replying HELP alerts the family at once.
- **Settings:**
  - Texting: `TWILIO_ACCOUNT_SID`, `TWILIO_AUTH_TOKEN`, `TWILIO_FROM` and `PUBLIC_URL`.
  - Email: `SMTP_HOST`, `SMTP_PORT` (587), `SMTP_USER`, `SMTP_PASSWORD` and `SMTP_FROM`.
  - `CARE_TIMEZONE` (such as `America/Chicago`) makes 08:00 the person's 08:00 on a server that runs on UTC.
- **Nothing pretends:** without the settings, every result says "not texted" or "not emailed" instead of
  pretending.
- **Not tested live yet:** these paths are tested with stand-ins for Twilio and the mail server, but not yet
  against live accounts. In the US, texting from an app number needs the operator to register it with
  carriers (10DLC).
- **Not a medical device:** it is a reminder and check-in tool, not a medical device and not an emergency
  service.

## Roadmap

- Voice-first app with wake-word-free "just talk" mode, large-text tablet UI
- Pharmacy refill integration, doctor-visit prep notes
- Scam screening on calls and texts (pairs with scam-shield)

## Development

Zero runtime dependencies; Python 3.10+.

```bash
python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -e ".[dev]"
python -m unittest discover -s tests -t .           # unit + CLI smoke tests
ruff check . && ruff format --check .               # lint + format
```

```
elder_companion/core.py       domain logic (pure, importable, fully tested)
elder_companion/__main__.py   CLI (`elder-companion ...` / `python -m elder_companion ...`)
tests/                unit tests + generated CLI smoke tests
```

CI runs lint and tests on Ubuntu and Windows across Python 3.10, 3.12 and 3.13.
Design, data model, trade-offs and production path: **[ARCHITECTURE.md](ARCHITECTURE.md)**.

Part of the [agent-economy](https://github.com/eliem08/agent-economy) portfolio (idea #29).
