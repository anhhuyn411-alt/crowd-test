"""Run one persona through a real browser session via browser-use."""

from __future__ import annotations

import os
import time
import traceback
from typing import Any, Callable

from crowdtest.clickfix import ensure_reliable_clicks
from crowdtest.persona import Persona
from crowdtest.results import PersonaResult, extract_report, parse_persona_report

LLMFactory = Callable[[], Any]

SALVAGE_PROMPT = """The message below is a QA persona's final report after testing
a website (or, if it never wrote one, its step-by-step working notes).
It was supposed to be ONLY a JSON object with this exact shape:

{{
  "goal_achieved": true or false,
  "satisfaction_score": integer 0-10,
  "summary": "one short paragraph",
  "findings": [
    {{"type": "bug|ux|accessibility|performance|content",
      "severity": "critical|major|minor",
      "title": "...", "description": "...", "where": "..."}}
  ]
}}

Convert the message into exactly that JSON object, preserving its meaning.
Only include findings the message actually claims; an empty list is valid.
Reply with ONLY the JSON object, no prose.

Message:
{message}
"""

# browser-use ships convenience extensions (ad blocking, cookie-banner
# auto-dismissal, URL cleaning). A testing tool must show personas the page as
# real users see it — cookie banners included — and we observed the extension
# stack interfering with site JS (phantom "broken button" findings). Users can
# re-enable by exporting BROWSER_USE_DISABLE_EXTENSIONS=0 before running.
os.environ.setdefault("BROWSER_USE_DISABLE_EXTENSIONS", "1")


async def run_persona(
    persona: Persona,
    url: str,
    llm_factory: LLMFactory,
    *,
    extra_goal: str | None = None,
    headless: bool = True,
    max_steps: int = 25,
) -> PersonaResult:
    """Spin up a fresh browser, let the persona use the site, return its report.

    Each persona gets its own Browser instance so parallel personas never share
    cookies, storage, or tabs.
    """
    from browser_use import Agent, Browser

    started = time.monotonic()
    result = PersonaResult(
        persona_name=persona.name, display_name=persona.display_name, ok=False
    )

    await ensure_reliable_clicks(headless=headless)

    browser = Browser(headless=headless)
    try:
        agent = Agent(
            task=persona.to_task_prompt(url, extra_goal),
            llm=llm_factory(),
            browser=browser,
        )
        history = await agent.run(max_steps=max_steps)

        result.steps = _safe_call(history, "number_of_steps")
        final_text = _safe_call(history, "final_result")
        try:
            report = extract_report(final_text)
        except ValueError:
            # Models sometimes sign off with prose instead of the JSON report,
            # or run out of steps without signing off at all. One conversion
            # call salvages the session instead of discarding everything the
            # persona observed (and the tokens it burned).
            report = await _salvage_report(
                final_text or _history_digest(history), llm_factory
            )
        (
            result.goal_achieved,
            result.satisfaction_score,
            result.summary,
            result.findings,
        ) = parse_persona_report(report)
        result.ok = True
    except Exception:
        result.error = traceback.format_exc(limit=3)
    finally:
        result.duration_s = round(time.monotonic() - started, 1)
        try:
            await browser.kill()
        except Exception:
            pass
    return result


def _history_digest(history: Any) -> str:
    """Reconstruct what the persona experienced from its step history.

    Used when the agent ran out of steps before writing any final answer.
    """
    parts: list[str] = []
    for thought in (_safe_call(history, "model_thoughts") or [])[-8:]:
        for attr in ("evaluation_previous_goal", "memory", "next_goal"):
            value = getattr(thought, attr, None)
            if value:
                parts.append(str(value))
    for content in (_safe_call(history, "extracted_content") or [])[-5:]:
        if content:
            parts.append(str(content))
    return "\n".join(parts)[:8000]


async def _salvage_report(final_text: str | None, llm_factory: LLMFactory) -> dict:
    """Turn a prose final answer into the report dict via one LLM call."""
    if not final_text or not final_text.strip():
        raise ValueError("agent produced no final answer")
    from browser_use.llm.messages import UserMessage

    llm = llm_factory()
    response = await llm.ainvoke(
        [UserMessage(content=SALVAGE_PROMPT.format(message=final_text[:8000]))]
    )
    return extract_report(response.completion)


def _safe_call(obj: Any, method: str) -> Any:
    """Call a history accessor, tolerating API drift across browser-use versions."""
    fn = getattr(obj, method, None)
    if fn is None:
        return None
    try:
        return fn()
    except Exception:
        return None
