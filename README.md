<!-- sell-kit:start -->
# Elder Companion

[![CI](https://github.com/eliem08/elder-companion/actions/workflows/ci.yml/badge.svg)](https://github.com/eliem08/elder-companion/actions/workflows/ci.yml)

> **A caring AI companion for older adults that keeps the family in the loop.**

**Who it's for:** Adult children caring for a parent who lives alone, and home-care agencies.

**The problem:** Missed medication, falls and loneliness go unnoticed until a crisis, and families can't check in every hour.

**What you get:** Medication reminders and adherence tracking, daily check-ins, red-flag escalations to family, and plain-language rewriting of confusing messages.

## Quickstart

Customers receive a release archive with the wheel and the examples. Python 3.10+ and no other dependencies.

```bash
pip install elder_companion-0.1.0-py3-none-any.whl
elder-companion demo
elder-companion simplify "Please authenticate via the portal in order to reschedule, subsequently you will receive a notification."
```

## Web app and API

Every command is also a JSON API endpoint and a browser form, served by the built-in web app.

```bash
elder-companion-web --port 8000          # then open http://127.0.0.1:8000
elder-companion-web keys create --label "first customer"   # prints an API key (stored hashed)
docker build -t elder-companion . && docker run -p 8000:8000 -e API_KEYS=sk_... -v elder-companion-data:/data elder-companion
```

Every API call needs `Authorization: Bearer <key>` once any key exists; a server on a public address refuses to start without one. Calls are rate-limited per key (60/min, `--rate`) and metered: `elder-companion-web usage` prints calls per key for billing.

Endpoints: `POST /api/demo`, `POST /api/simplify`, plus `GET /healthz` and `GET /api/spec` (machine-readable field list).
Files are sent as `{"name": ..., "content": ...}`, folders as `{"files": [...]}` or a base64 zip.

## Pricing

Every plan starts with a 14-day free trial. Prices in USD, billed monthly unless noted.

| Plan | Price | Includes |
|---|---|---|
| **Family** | $19 per month | 1 loved one; Reminders and check-ins; Daily family digest |
| **Family Plus** | $39 per month | 2 loved ones; Instant red-flag alerts; Up to 5 family members |
| **Care Agency** | $9 per client per month | Caseload dashboard; Escalation routing; Priority support |

To start a trial or buy a plan, email **sales@YOUR-DOMAIN.com**.

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
- **Plain-language rewriter** for anything the companion reads aloud:
  jargon → everyday words, long sentences split, Flesch reading-ease score

## Quickstart

```bash
pip install -e .
elder-companion demo
elder-companion simplify "Please authenticate via the portal to reschedule your appointment, subsequently..."
```

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
