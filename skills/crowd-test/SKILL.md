---
name: crowd-test
description: Unleash a mob of AI virtual users (impatient shoppers, confused seniors, keyboard-only users, chaos monkeys) on a website to stress-test its UX and hunt bugs. Use when the user asks to "crowd test", "mob test", "send virtual users", or wants persona-based UX/QA feedback on a URL before launch.
---

# crowd-test: let the mob loose on a website

crowd-test sends AI personas through a site in real browsers. Each persona
role-plays a human (limited patience, limited tech skill, their own goals),
files findings, and the crew's report ends in a **survival grade** (S = the mob
couldn't lay a finger on it … F = the mob destroyed it).

## Ground rule (non-negotiable)

Only point crowd-test at sites the user owns or has permission to test. If the
target clearly isn't theirs (a competitor, a production site of someone else),
ask before running.

## Setup check

```bash
crowd-test --help || pip install crowd-test
```

An LLM key must be set: `ANTHROPIC_API_KEY` or `OPENAI_API_KEY`. If neither is
set, stop and ask the user for one — do not guess.

Optional extras the user may want:

```bash
pip install crowd-test[probe]      # cross-engine verification (--cross-verify)
playwright install chromium        # one-time browser download for the probe
pip install git+https://github.com/microsoft/Webwright   # third harness (--tribunal)
```

## Running

Start small (fast, cheap), escalate only if the user wants a full siege:

```bash
# Quick pass: 3 named ringleaders
crowd-test run https://TARGET --personas mai-impatient-shopper,harold-the-senior,kai-keyboard-only

# Full built-in crew (10 personas)
crowd-test run https://TARGET

# Siege: crew + 10 random mob members, findings cross-checked in a second engine
crowd-test run https://TARGET --mob 10 --seed 42 --cross-verify

# Full tribunal: three independent harnesses must agree before a bug counts
crowd-test run https://TARGET --tribunal

# CI mode: fail the build on any verified critical
crowd-test run https://TARGET --cross-verify --fail-on-critical
```

Useful flags: `--goal "try to buy the cheapest item"` (extra mission for every
persona), `--concurrency 5`, `--max-steps 40`, `--headed` (watch the browsers),
`--out DIR` (default `crowd-test-reports/`).

`crowd-test list-personas` shows the built-in cast. Custom personas are plain
YAML passed with `--persona-file` — see the repo README for the schema.

## Interpreting the run

Reports land in `crowd-test-reports/`: `report.md`, `report.html` (dark-theme,
shareable), `results.json` (machine-readable).

- **Survival grade**: S (≥95), A (≥85), B (≥70), C (≥55), D (≥40), F (below).
  Critical findings cost 25 points, major 10, minor 3, blended with the mob's
  satisfaction scores.
- **Verification badges**: ✅ verified, ⚠️ not reproduced, 🔬 disputed by
  cross-engine probe. Disputed/not-reproduced findings are shown but excluded
  from the grade — they're usually automation artifacts, not real bugs.
- Exit codes: 0 ok, 1 crew failed to complete, 2 critical findings present
  (with `--fail-on-critical`).

After a run, summarize for the user: the grade, the verified criticals first
(with the persona quote and where it happened), then majors, then patterns
across personas (e.g. three different personas all stalled on the same form).
Offer concrete fixes for the top findings — the report gives you the raw
material, the user wants the "so what".
