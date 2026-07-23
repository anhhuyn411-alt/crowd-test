"""The detective: an independent skeptical agent that tries to reproduce findings.

Persona agents are dramatic by design — that is what makes their reports vivid.
The cost is the occasional false accusation (a stale screenshot, a mis-click).
Before a critical or major finding counts toward the survival grade, a fresh
agent with no persona and no memory of the accusation attempts to reproduce it.
"""

from __future__ import annotations

import traceback

from crowdtest.results import Finding, extract_report
from crowdtest.runner import LLMFactory, _safe_call

VERIFY_PROMPT = """You are a rigorous, skeptical QA engineer. You do NOT role-play.

A virtual user testing {url} reported this issue:

- Title: {title}
- Where: {where}
- What they claim: {description}

Your job is to independently REPRODUCE it — or refute it. Rules:
- Start from a clean load of {url} and follow the most plausible path to the
  reported location yourself.
- Attempt the failing action carefully, waiting for the page to settle after
  each step. If it seems to fail, reload the page and attempt it once more
  cleanly before concluding.
- You are checking the SITE, not the reporter. A claim you cannot reproduce
  after honest attempts is "not reproduced" — that is a perfectly good outcome.
- If the location or action in the claim doesn't exist at all, that also means
  "not reproduced".

Your step budget is small. Keep the investigation tight and ALWAYS reserve your
final step for the verdict, even if the investigation feels unfinished.

Your VERY LAST message must be ONLY a JSON object, no prose around it:

{{
  "reproduced": true,
  "notes": "One or two sentences: what you did and what you observed."
}}
"""


async def verify_finding(
    finding: Finding,
    url: str,
    llm_factory: LLMFactory,
    *,
    headless: bool = True,
    max_steps: int = 12,
) -> Finding:
    """Return the finding annotated with the detective's verdict.

    A verification that itself crashes leaves the finding unverified rather
    than refuted — the benefit of the doubt goes to the reporter.
    """
    from browser_use import Agent, Browser

    from crowdtest.clickfix import ensure_reliable_clicks

    await ensure_reliable_clicks(headless=headless)

    browser = Browser(headless=headless)
    try:
        agent = Agent(
            task=VERIFY_PROMPT.format(
                url=url,
                title=finding.title,
                where=finding.where or "(not specified)",
                description=finding.description or finding.title,
            ),
            llm=llm_factory(),
            browser=browser,
        )
        history = await agent.run(max_steps=max_steps)
        verdict = extract_report(_safe_call(history, "final_result"))
        finding.verified = (
            "confirmed" if bool(verdict.get("reproduced")) else "not_reproduced"
        )
        finding.verify_notes = str(verdict.get("notes", "")).strip()
    except ValueError:
        finding.verified = ""
        finding.verify_notes = "detective could not reach a verdict (no report)"
    except Exception:
        finding.verified = ""
        finding.verify_notes = (
            "detective session crashed: "
            + traceback.format_exc(limit=0).strip().splitlines()[-1]
        )
    finally:
        try:
            await browser.kill()
        except Exception:
            pass
    return finding
