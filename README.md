# elder-companion

[![CI](https://github.com/eliem08/elder-companion/actions/workflows/ci.yml/badge.svg)](https://github.com/eliem08/elder-companion/actions/workflows/ci.yml)

> **A personal AI companion for older adults** (and other high-LTV niches).

General-purpose assistants are built for 30-year-old power users. Older
adults need something different: fewer features, bigger words, gentle
routines, and a quiet line back to their family when something's off. It's a
high-LTV niche — families pay monthly for peace of mind.

This repo is the companion's care engine (the voice/chat UI sits on top).

## What the MVP does

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
