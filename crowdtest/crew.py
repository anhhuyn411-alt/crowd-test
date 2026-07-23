"""Orchestrate a crowd of personas against one URL, concurrently."""

from __future__ import annotations

import asyncio
from typing import Callable

from crowdtest.persona import Persona
from crowdtest.probe import cross_probe
from crowdtest.results import CrewResult, PersonaResult
from crowdtest.runner import LLMFactory, run_persona
from crowdtest.tribunal import tribunal_verify
from crowdtest.verify import verify_finding

ProgressHook = Callable[[str, str], None]

VERIFIED_SEVERITIES = ("critical", "major")


async def run_crew(
    personas: list[Persona],
    url: str,
    llm_factory: LLMFactory,
    *,
    extra_goal: str | None = None,
    headless: bool = True,
    max_steps: int = 25,
    concurrency: int = 3,
    verify: bool = False,
    cross: bool = False,
    tribunal: bool = False,
    provider: str = "anthropic",
    on_progress: ProgressHook | None = None,
) -> CrewResult:
    """Run every persona through the site, at most *concurrency* at a time.

    With *verify* on, every critical/major finding is handed to an independent
    detective agent that tries to reproduce it; refuted findings stay in the
    report but stop counting toward the survival grade.
    """
    semaphore = asyncio.Semaphore(max(1, concurrency))

    async def run_one(persona: Persona) -> PersonaResult:
        async with semaphore:
            if on_progress:
                on_progress(persona.name, "started")
            result = await run_persona(
                persona,
                url,
                llm_factory,
                extra_goal=extra_goal,
                headless=headless,
                max_steps=max_steps,
            )
            if on_progress:
                status = "done" if result.ok else "failed"
                on_progress(persona.name, status)

        if verify and result.ok:
            for finding in result.findings:
                if finding.severity not in VERIFIED_SEVERITIES:
                    continue
                async with semaphore:
                    if on_progress:
                        on_progress(f"verify: {finding.title[:40]}", "started")
                    await verify_finding(
                        finding, url, llm_factory, headless=headless
                    )
                    # The probe is independent of the detective: it must run
                    # even when the detective is inconclusive, because a stack
                    # artifact blinds the detective and the mob alike. Only a
                    # clean refutation makes a second opinion unnecessary.
                    if cross and finding.verified != "not_reproduced":
                        await cross_probe(
                            finding, url, llm_factory, headless=headless
                        )
                    # Same reasoning as the probe: only a clean refutation
                    # spares the finding a third opinion.
                    if tribunal and finding.verified != "not_reproduced":
                        await tribunal_verify(
                            finding, url, provider, headless=headless
                        )
                    if on_progress:
                        on_progress(
                            f"verify: {finding.title[:40]}",
                            finding.verified or "inconclusive",
                        )
        return result

    results = await asyncio.gather(*(run_one(p) for p in personas))
    return CrewResult(url=url, results=list(results))
