"""Cross-engine forensics: re-check a confirmed finding in a second browser stack.

The mob and the detective both drive the same automation engine. If that engine
itself glitches on a site (a click that doesn't land, a stale screenshot), they
agree on a bug that isn't there. The probe breaks the echo chamber: an LLM
translates the finding into a tiny declarative repro script — plain data, never
code — and a Playwright-driven interpreter (a completely independent browser
stack) executes it.

Outcomes:
- probe reproduces the bug  -> the finding stands ("confirmed")
- probe shows it working    -> the finding is re-marked "disputed" (likely an
  automation artifact) and stops counting toward the survival grade
- probe can't be built/run  -> inconclusive; the finding keeps its status
"""

from __future__ import annotations

import json
import re

from crowdtest.results import Finding

PROBE_ACTIONS = {"goto", "click", "fill", "press", "wait_for", "wait_ms"}
PROBE_CHECKS = {
    "visible",
    "not_visible",
    "text_contains",
    "text_not_contains",
    "url_contains",
    "url_not_contains",
}

PROBE_PROMPT = """You translate a bug report into a minimal, deterministic repro script.

Site under test: {url}

The bug report:
- Title: {title}
- Where: {where}
- Description: {description}

Produce a JSON object (ONLY JSON, no prose) with this exact shape:

{{
  "feasible": true,
  "steps": [
    {{"action": "goto", "value": "{url}"}},
    {{"action": "fill", "selector": "#user-name", "value": "standard_user"}},
    {{"action": "click", "selector": "#login-button"}},
    {{"action": "wait_ms", "value": "1000"}}
  ],
  "bug_present_when": {{"check": "not_visible", "selector": ".shopping_cart_badge", "value": ""}},
  "notes": "One sentence on what the script does."
}}

Rules:
- Allowed actions: goto, click, fill, press, wait_for (selector), wait_ms (milliseconds).
- Allowed checks: visible, not_visible, text_contains, text_not_contains,
  url_contains, url_not_contains. For text checks, "selector" may be "body".
- Use concrete CSS selectors. Prefer ids and stable attributes mentioned in the
  report. If the report names credentials or test accounts, use them.
- "bug_present_when" must be true exactly when the reported bug EXISTS.
- Maximum 12 steps. If the bug cannot be checked deterministically this way
  (needs payment, email, random content), return {{"feasible": false, "notes": "why"}}.
"""


def _extract_json(text: str) -> dict:
    fenced = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
    raw = fenced.group(1) if fenced else text[text.find("{") : text.rfind("}") + 1]
    return json.loads(raw)


def validate_script(script: dict) -> str | None:
    """Return an error string if the LLM-produced script is malformed."""
    if not script.get("feasible"):
        return "probe not feasible: " + str(script.get("notes", "no reason given"))
    steps = script.get("steps") or []
    if not steps or len(steps) > 12:
        return "probe script has no steps or too many"
    for step in steps:
        if step.get("action") not in PROBE_ACTIONS:
            return f"unknown probe action: {step.get('action')}"
    condition = script.get("bug_present_when") or {}
    if condition.get("check") not in PROBE_CHECKS:
        return f"unknown probe check: {condition.get('check')}"
    return None


async def _execute(script: dict, headless: bool = True) -> bool:
    """Run the script in Playwright; return True when the bug-present condition holds."""
    from playwright.async_api import async_playwright

    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=headless)
        page = await browser.new_page()
        page.set_default_timeout(8000)
        try:
            for step in script["steps"]:
                action = step["action"]
                selector = step.get("selector", "")
                value = str(step.get("value", ""))
                if action == "goto":
                    await page.goto(value, wait_until="load")
                elif action == "click":
                    await page.click(selector)
                elif action == "fill":
                    await page.fill(selector, value)
                elif action == "press":
                    await page.press(selector or "body", value or "Enter")
                elif action == "wait_for":
                    await page.wait_for_selector(selector)
                elif action == "wait_ms":
                    await page.wait_for_timeout(min(int(value or 500), 5000))

            cond = script["bug_present_when"]
            check = cond["check"]
            selector = cond.get("selector", "body")
            value = str(cond.get("value", ""))
            if check in ("visible", "not_visible"):
                visible = await page.is_visible(selector)
                return visible if check == "visible" else not visible
            if check in ("text_contains", "text_not_contains"):
                text = await page.text_content(selector) or ""
                contains = value in text
                return contains if check == "text_contains" else not contains
            if check in ("url_contains", "url_not_contains"):
                contains = value in page.url
                return contains if check == "url_contains" else not contains
            raise ValueError(f"unhandled check {check}")
        finally:
            await browser.close()


async def cross_probe(finding: Finding, url: str, llm_factory, *, headless: bool = True) -> Finding:
    """Second-opinion pass on a detective-confirmed finding.

    Only downgrades, never upgrades: a probe that reproduces the bug simply
    leaves "confirmed" in place; a probe that can't run leaves things as-is.
    """
    try:
        from playwright.async_api import async_playwright  # noqa: F401
    except ImportError:
        finding.verify_notes += (
            " | cross-engine probe skipped: install with pip install crowd-test[probe]"
        )
        return finding

    from browser_use.llm.messages import UserMessage

    try:
        llm = llm_factory()
        response = await llm.ainvoke(
            [
                UserMessage(
                    content=PROBE_PROMPT.format(
                        url=url,
                        title=finding.title,
                        where=finding.where or "(not specified)",
                        description=finding.description or finding.title,
                    )
                )
            ]
        )
        script = _extract_json(response.completion)
        error = validate_script(script)
        if error:
            finding.verify_notes += f" | cross-engine probe inconclusive ({error})"
            return finding

        bug_present = await _execute(script, headless=headless)
        if bug_present:
            finding.verify_notes += " | cross-engine probe: reproduced in Playwright too"
        else:
            finding.verified = "disputed"
            finding.verify_notes += (
                " | cross-engine probe: works fine in an independent browser — "
                "likely an automation artifact, excluded from grade"
            )
    except Exception as exc:  # probe is best-effort by design
        finding.verify_notes += f" | cross-engine probe errored ({type(exc).__name__})"
    return finding
