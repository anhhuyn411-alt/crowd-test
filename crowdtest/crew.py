"""Orchestrate a crowd of personas against one URL, concurrently."""

from __future__ import annotations

import asyncio
from typing import Callable

from crowdtest.persona import Persona
from crowdtest.results import CrewResult, PersonaResult
from crowdtest.runner import LLMFactory, run_persona

ProgressHook = Callable[[str, str], None]


async def run_crew(
    personas: list[Persona],
    url: str,
    llm_factory: LLMFactory,
    *,
    extra_goal: str | None = None,
    headless: bool = True,
    max_steps: int = 25,
    concurrency: int = 3,
    on_progress: ProgressHook | None = None,
) -> CrewResult:
    """Run every persona through the site, at most *concurrency* at a time."""
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
            return result

    results = await asyncio.gather(*(run_one(p) for p in personas))
    return CrewResult(url=url, results=list(results))
