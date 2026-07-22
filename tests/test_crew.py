import asyncio

import crowdtest.crew as crew_mod
from crowdtest.crew import run_crew
from crowdtest.persona import load_builtin_personas
from crowdtest.results import PersonaResult


def test_run_crew_respects_concurrency_and_collects_results(monkeypatch):
    personas = load_builtin_personas()
    active = 0
    peak = 0

    async def fake_run_persona(persona, url, llm_factory, **kwargs):
        nonlocal active, peak
        active += 1
        peak = max(peak, active)
        await asyncio.sleep(0.01)
        active -= 1
        return PersonaResult(
            persona_name=persona.name,
            display_name=persona.display_name,
            ok=True,
            satisfaction_score=7,
        )

    monkeypatch.setattr(crew_mod, "run_persona", fake_run_persona)

    events = []
    crew = asyncio.run(
        run_crew(
            personas,
            "https://example.com",
            llm_factory=lambda: None,
            concurrency=2,
            on_progress=lambda name, status: events.append((name, status)),
        )
    )

    assert len(crew.results) == len(personas)
    assert peak <= 2
    assert all(r.ok for r in crew.results)
    assert ("rex-chaos-monkey", "done") in events


def test_run_crew_survives_persona_failure(monkeypatch):
    personas = load_builtin_personas(["mai-impatient-shopper", "rex-chaos-monkey"])

    async def flaky_run_persona(persona, url, llm_factory, **kwargs):
        if persona.name == "rex-chaos-monkey":
            return PersonaResult(
                persona_name=persona.name,
                display_name=persona.display_name,
                ok=False,
                error="boom",
            )
        return PersonaResult(
            persona_name=persona.name,
            display_name=persona.display_name,
            ok=True,
        )

    monkeypatch.setattr(crew_mod, "run_persona", flaky_run_persona)
    crew = asyncio.run(
        run_crew(personas, "https://example.com", llm_factory=lambda: None)
    )
    assert len(crew.completed) == 1
    assert len(crew.results) == 2
