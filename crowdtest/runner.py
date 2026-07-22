"""Run one persona through a real browser session via browser-use."""

from __future__ import annotations

import time
import traceback
from typing import Any, Callable

from crowdtest.persona import Persona
from crowdtest.results import PersonaResult, extract_report, parse_persona_report

LLMFactory = Callable[[], Any]


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

    browser = Browser(headless=headless)
    try:
        agent = Agent(
            task=persona.to_task_prompt(url, extra_goal),
            llm=llm_factory(),
            browser=browser,
        )
        history = await agent.run(max_steps=max_steps)

        result.steps = _safe_call(history, "number_of_steps")
        report = extract_report(_safe_call(history, "final_result"))
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


def _safe_call(obj: Any, method: str) -> Any:
    """Call a history accessor, tolerating API drift across browser-use versions."""
    fn = getattr(obj, method, None)
    if fn is None:
        return None
    try:
        return fn()
    except Exception:
        return None
