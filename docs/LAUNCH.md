# Launch playbook (internal — not part of the product docs)

Status 2026-07-23: core v0.5.0 + crowd-test-mcp v0.1.0 both live on PyPI,
CI green, README image renders, awesome-claude-skills PR #1412 open.
The only missing asset is a real demo run (blocked on API credits) — launch
can go without it; post the GIF in replies later.

## Show HN (the main event)

**Title (78 chars max, no emoji, no exclamation):**
> Show HN: Crowd-test – a mob of AI personas attacks your site, 3 engines verify

**URL:** https://github.com/anhhuyn411-alt/crowd-test

**Body:**

I built crowd-test because every launch taught me the same lesson: unit tests
pass, E2E tests pass, and then real users immediately hit problems no test
anticipated — because tests behave, and users don't.

crowd-test sends AI personas into your site in real browsers: a 72-year-old
who can't see unlabeled icons, an impatient shopper who abandons anything
longer than 3 steps, a keyboard-only user, a privacy hawk who rejects every
banner, and a chaos monkey typing emoji into your forms. Each reports findings
in character, and your app gets a survival grade from S to F.

The part I think is genuinely interesting: verification. Persona agents are
dramatic by design, and worse — browser automation itself sometimes glitches,
and then every agent on the same stack hallucinates the same bug. This
happened to me on day one: the whole mob unanimously convicted an innocent
add-to-cart button, because the automation layer was eating the clicks. The
site was fine.

So findings face a tribunal of up to three independent harnesses before they
count: a skeptical detective agent (same stack, no persona), a declarative
repro script executed by raw Playwright (different stack — this one catches
the automation artifacts), and optionally a Microsoft Webwright agent as a
third opinion. A bug only bleeds your grade when an independent engine
reproduces it.

Personas are 20-line YAML files — the dream is a community folder of
ringleaders ("skeptical grandmother", "user on a broken trackpad"). There's
also a Claude Code skill and an MCP server (crowd-test-mcp) so your coding
agent can run the mob and read the report itself.

MIT licensed, built on browser-use. Bring your own Anthropic/OpenAI key.
Honest limitations: it's not load testing, it's not a replacement for real
user research, and LLM costs are yours.

**First comment (post immediately, from your account):** nothing — save the
phantom-click forensics story details, cost numbers ("a 10-persona run costs
roughly $X with Sonnet"), and the sample report link for replies.

## Product Hunt

- **Name:** crowd-test
- **Tagline:** Your app, versus a mob of AI users
- **Description:** AI personas — impatient shoppers, seniors, keyboard-only
  users, chaos monkeys — attack your site in real browsers. Three independent
  engines verify every accusation. You get a damage report and a survival
  grade from S to F.
- **First comment:** origin story + honest limitations (not load testing, not
  a replacement for user research, LLM costs are yours) + the phantom-click
  story.

## X/Twitter thread opener

> I let a mob of AI users loose on my app.
>
> A 72-year-old couldn't find my menu. An impatient shopper rage-quit my
> checkout. A chaos monkey got my address form to 500.
>
> Survival grade: D.
>
> Open source: https://github.com/anhhuyn411-alt/crowd-test

Thread beats: (2) the mob table screenshot, (3) the phantom-click story →
tribunal diagram, (4) 20-line YAML persona, (5) skill + MCP ("your coding
agent runs the mob for you"), (6) call for community ringleaders.

## Distribution list (after HN, same week)

- [ ] browser-use Discord/community showcase (they love ecosystem tools)
- [ ] r/webdev, r/QualityAssurance, r/SideProject, r/ClaudeAI (MCP angle)
- [ ] MCP server directories: modelcontextprotocol/servers community list,
      mcp.so, PulseMCP, Smithery — submit crowd-test-mcp to each
- [ ] awesome-ai-testing / awesome-mcp-servers PRs
- [ ] dev.to write-up: "The mob unanimously convicted an innocent button" —
      the false-positive forensics story is the hook, tool is the payoff

## Cadence

Launch Tue–Thu, ~14:00–16:00 UTC (HN morning US). Reply to every comment in
the first 3 hours — comment velocity is what keeps a Show HN alive. Have the
sample report (examples/sample-report.html) ready to link; post the real
`--mob 10 --tribunal` GIF in replies once credits are topped up.
