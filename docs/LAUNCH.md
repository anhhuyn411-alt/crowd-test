# Launch playbook (internal — not part of the product docs)

## Pre-launch checklist

- [ ] PyPI publish live (`pip install crowd-test` works on a clean machine)
- [ ] README demo image renders on GitHub
- [ ] CI green on main
- [ ] One real-world report you're allowed to share (your own site)

## Show HN

**Title:**
> Show HN: Crowd-test – unleash a mob of AI personas on your web app

**Body draft:**

I built crowd-test because every launch taught me the same lesson: unit tests
pass, E2E tests pass, and then real users immediately hit problems no test
anticipated — because tests behave, and users don't.

crowd-test sends AI personas into your site in real browsers: a 72-year-old
who can't see unlabeled icons, an impatient shopper who abandons anything
longer than 3 steps, a keyboard-only user, a privacy hawk who rejects every
banner, and a chaos monkey typing emoji into your forms. Each reports findings
in character, and your app gets a survival grade from S to F.

Two design decisions I think are interesting:

1. Findings are adversarially verified. Persona agents are dramatic by design,
   so every critical accusation goes to a "detective" agent that tries to
   reproduce it — and optionally to a cross-engine probe in a second browser
   stack, which catches false positives caused by the automation layer itself
   (this happened to me in testing; the mob unanimously convicted an innocent
   button).

2. Personas are 20-line YAML files. The dream is a community folder of
   ringleaders — "skeptical grandmother", "user on a broken trackpad" — that
   you can throw at your app.

MIT licensed, built on browser-use. Bring your own Anthropic/OpenAI key.

## Product Hunt

- **Tagline:** Your app, versus a mob of AI users
- **First comment:** the origin story + honest limitations (not load testing,
  not a replacement for real user research, LLM costs are yours)

## X/Twitter thread opener

> I let a mob of AI users loose on my app.
>
> A 72-year-old couldn't find my menu. An impatient shopper rage-quit my
> checkout. A chaos monkey got my address form to 500.
>
> Survival grade: D.
>
> Open source: [link]

## Distribution list

- [ ] PR adding crowd-test to awesome-ai-testing
- [ ] browser-use Discord/community showcase
- [ ] r/webdev, r/QualityAssurance, r/SideProject
- [ ] dev.to / Hashnode write-up: "My app failed its first mob test"

## Cadence

Launch Tue–Thu, ~14:00–16:00 UTC (HN morning US). Reply to every comment in
the first 3 hours. Have the `--mob 50` demo GIF ready to post in replies.
