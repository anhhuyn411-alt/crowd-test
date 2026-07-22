import asyncio

import crowdtest.crew as crew_mod
from crowdtest.crew import run_crew
from crowdtest.persona import load_builtin_personas
from crowdtest.probe import _extract_json, validate_script
from crowdtest.report import build_markdown
from crowdtest.results import CrewResult, Finding, PersonaResult


VALID_SCRIPT = {
    "feasible": True,
    "steps": [
        {"action": "goto", "value": "https://example.com"},
        {"action": "click", "selector": "#btn"},
    ],
    "bug_present_when": {"check": "not_visible", "selector": ".badge", "value": ""},
}


def test_validate_script_accepts_valid():
    assert validate_script(VALID_SCRIPT) is None


def test_validate_script_rejects_bad_shapes():
    assert "not feasible" in validate_script({"feasible": False, "notes": "captcha"})
    assert "no steps" in validate_script({"feasible": True, "steps": []})
    bad_action = dict(VALID_SCRIPT, steps=[{"action": "evaluate", "value": "x"}])
    assert "unknown probe action" in validate_script(bad_action)
    bad_check = dict(VALID_SCRIPT, bug_present_when={"check": "exists"})
    assert "unknown probe check" in validate_script(bad_check)
    too_many = dict(VALID_SCRIPT, steps=[{"action": "wait_ms", "value": "1"}] * 13)
    assert "too many" in validate_script(too_many)


def test_extract_json_handles_fences():
    assert _extract_json('```json\n{"feasible": true}\n```')["feasible"] is True
    assert _extract_json('noise {"a": 1} noise')["a"] == 1


def test_disputed_findings_excluded_from_grade_but_shown():
    crew = CrewResult(
        url="https://example.com",
        results=[
            PersonaResult(
                persona_name="p", display_name="P", ok=True, satisfaction_score=8,
                findings=[
                    Finding(
                        type="bug", severity="critical", title="Phantom click bug",
                        verified="disputed",
                        verify_notes="cross-engine probe: works fine",
                    )
                ],
            )
        ],
    )
    assert crew.findings_by_severity()["critical"] == 0
    assert crew.survival_grade() in ("S", "A")
    md = build_markdown(crew, generated_at="2026-07-22")
    assert "Phantom click bug" in md
    assert "disputed by cross-engine probe" in md


def test_crew_probes_only_confirmed_findings(monkeypatch):
    personas = load_builtin_personas(["mai-impatient-shopper"])
    probed = []

    async def fake_run_persona(persona, url, llm_factory, **kwargs):
        return PersonaResult(
            persona_name=persona.name, display_name=persona.display_name, ok=True,
            findings=[
                Finding(type="bug", severity="critical", title="ConfirmMe"),
                Finding(type="bug", severity="major", title="RefuteMe"),
                Finding(type="bug", severity="major", title="InconclusiveMe"),
            ],
        )

    async def fake_verify(finding, url, llm_factory, **kwargs):
        if finding.title == "ConfirmMe":
            finding.verified = "confirmed"
        elif finding.title == "RefuteMe":
            finding.verified = "not_reproduced"
        else:
            finding.verified = ""  # detective couldn't reach a verdict
        return finding

    async def fake_probe(finding, url, llm_factory, **kwargs):
        probed.append(finding.title)
        finding.verified = "disputed"
        return finding

    monkeypatch.setattr(crew_mod, "run_persona", fake_run_persona)
    monkeypatch.setattr(crew_mod, "verify_finding", fake_verify)
    monkeypatch.setattr(crew_mod, "cross_probe", fake_probe)

    crew = asyncio.run(
        run_crew(
            personas, "https://example.com", llm_factory=lambda: None,
            verify=True, cross=True,
        )
    )
    # Refuted finding never probed; confirmed AND inconclusive both are —
    # a stack artifact can blind the detective too.
    assert sorted(probed) == ["ConfirmMe", "InconclusiveMe"]
    assert crew.findings_by_severity() == {"critical": 0, "major": 0, "minor": 0}
