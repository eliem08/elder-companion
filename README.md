# elder-companion

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
