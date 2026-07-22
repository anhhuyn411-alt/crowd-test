import asyncio

import crowdtest.crew as crew_mod
from crowdtest.crew import run_crew
from crowdtest.persona import load_builtin_personas
from crowdtest.report import build_markdown
from crowdtest.results import CrewResult, Finding, PersonaResult


def crew_with_findings(findings) -> CrewResult:
    return CrewResult(
        url="https://example.com",
        results=[
            PersonaResult(
                persona_name="mai-impatient-shopper",
                display_name="Mai",
                ok=True,
                satisfaction_score=5,
                findings=findings,
            )
        ],
    )


def test_refuted_findings_do_not_count_toward_grade():
    real = Finding(
        type="bug", severity="critical", title="Real bug", verified="confirmed"
    )
    ghost = Finding(
        type="bug", severity="critical", title="Ghost bug", verified="not_reproduced"
    )
    crew = crew_with_findings([real, ghost])
    assert crew.findings_by_severity()["critical"] == 1
    # But the report still shows both.
    assert len(crew.all_findings) == 2


def test_report_shows_verification_badges():
    crew = crew_with_findings(
        [
            Finding(
                type="bug", severity="critical", title="Real bug",
                verified="confirmed", verify_notes="Reproduced on first try.",
            ),
            Finding(
                type="bug", severity="major", title="Ghost bug",
                verified="not_reproduced", verify_notes="Worked fine twice.",
            ),
        ]
    )
    md = build_markdown(crew, generated_at="2026-07-22")
    assert "✅" in md and "verified by detective" in md
    assert "could not be reproduced" in md
    assert "Worked fine twice." in md


def test_run_crew_verifies_only_critical_and_major(monkeypatch):
    personas = load_builtin_personas(["mai-impatient-shopper"])
    verified_titles = []

    async def fake_run_persona(persona, url, llm_factory, **kwargs):
        return PersonaResult(
            persona_name=persona.name,
            display_name=persona.display_name,
            ok=True,
            findings=[
                Finding(type="bug", severity="critical", title="C"),
                Finding(type="ux", severity="minor", title="M"),
                Finding(type="bug", severity="major", title="J"),
            ],
        )

    async def fake_verify(finding, url, llm_factory, **kwargs):
        verified_titles.append(finding.title)
        finding.verified = "confirmed"
        return finding

    monkeypatch.setattr(crew_mod, "run_persona", fake_run_persona)
    monkeypatch.setattr(crew_mod, "verify_finding", fake_verify)

    crew = asyncio.run(
        run_crew(
            personas, "https://example.com", llm_factory=lambda: None, verify=True
        )
    )
    assert sorted(verified_titles) == ["C", "J"]  # minor "M" skipped
    assert crew.results[0].findings[0].verified == "confirmed"


def test_run_crew_skips_verification_by_default(monkeypatch):
    personas = load_builtin_personas(["mai-impatient-shopper"])

    async def fake_run_persona(persona, url, llm_factory, **kwargs):
        return PersonaResult(
            persona_name=persona.name,
            display_name=persona.display_name,
            ok=True,
            findings=[Finding(type="bug", severity="critical", title="C")],
        )

    async def exploding_verify(finding, url, llm_factory, **kwargs):
        raise AssertionError("verify must not run when verify=False")

    monkeypatch.setattr(crew_mod, "run_persona", fake_run_persona)
    monkeypatch.setattr(crew_mod, "verify_finding", exploding_verify)

    crew = asyncio.run(
        run_crew(personas, "https://example.com", llm_factory=lambda: None)
    )
    assert crew.results[0].findings[0].verified == ""
