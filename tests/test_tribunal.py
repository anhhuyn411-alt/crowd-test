import asyncio
import json

import crowdtest.crew as crew_mod
import crowdtest.tribunal as tribunal_mod
from crowdtest.crew import run_crew
from crowdtest.persona import load_builtin_personas
from crowdtest.results import Finding, PersonaResult
from crowdtest.tribunal import config_for_provider, find_verdict, tribunal_verify


def make_finding(**kwargs) -> Finding:
    defaults = dict(type="bug", severity="critical", title="Cart broken")
    defaults.update(kwargs)
    return Finding(**defaults)


def test_config_for_provider():
    assert config_for_provider("anthropic") == "model_claude.yaml"
    assert config_for_provider("openai") == "model_openai.yaml"


def test_find_verdict_prefers_verdict_json(tmp_path):
    run_dir = tmp_path / "crowdtest-tribunal_20260723" / "workspace"
    run_dir.mkdir(parents=True)
    (run_dir / "verdict.json").write_text(
        json.dumps({"bug_present": False, "notes": "cart works"}), encoding="utf-8"
    )
    (tmp_path / "trajectory.jsonl").write_text(
        '{"step": 1, "bug_present": true}', encoding="utf-8"
    )
    verdict = find_verdict(tmp_path)
    assert verdict["bug_present"] is False


def test_find_verdict_falls_back_to_artifact_scan(tmp_path):
    (tmp_path / "trajectory.jsonl").write_text(
        'agent said: {"bug_present": true, "notes": "still broken"} end',
        encoding="utf-8",
    )
    verdict = find_verdict(tmp_path)
    assert verdict["bug_present"] is True


def test_find_verdict_none_when_no_artifacts(tmp_path):
    assert find_verdict(tmp_path) is None


def test_missing_webwright_appends_install_hint(monkeypatch):
    monkeypatch.setattr(tribunal_mod, "webwright_available", lambda: False)
    finding = make_finding(verified="confirmed")
    result = asyncio.run(tribunal_verify(finding, "https://example.com", "anthropic"))
    assert result.verified == "confirmed"  # unchanged
    assert "pip install git+https://github.com/microsoft/Webwright" in result.verify_notes


def run_tribunal_with_verdict(monkeypatch, finding, verdict):
    monkeypatch.setattr(tribunal_mod, "webwright_available", lambda: True)
    monkeypatch.setattr(tribunal_mod, "_run_webwright", lambda *a, **k: None)
    monkeypatch.setattr(tribunal_mod, "find_verdict", lambda _dir: verdict)
    return asyncio.run(tribunal_verify(finding, "https://example.com", "anthropic"))


def test_disputes_unreproduced_finding(monkeypatch):
    finding = make_finding(verified="")
    result = run_tribunal_with_verdict(
        monkeypatch, finding, {"bug_present": False, "notes": "works"}
    )
    assert result.verified == "disputed"


def test_dissents_instead_of_overruling_confirmed(monkeypatch):
    finding = make_finding(verified="confirmed")
    result = run_tribunal_with_verdict(
        monkeypatch, finding, {"bug_present": False, "notes": "works"}
    )
    assert result.verified == "confirmed"
    assert "dissents" in result.verify_notes


def test_upgrades_inconclusive_to_confirmed_on_repro(monkeypatch):
    finding = make_finding(verified="")
    result = run_tribunal_with_verdict(
        monkeypatch, finding, {"bug_present": True, "notes": "broken here too"}
    )
    assert result.verified == "confirmed"
    assert "reproduced independently" in result.verify_notes


def test_inconclusive_when_no_verdict(monkeypatch):
    finding = make_finding(verified="confirmed")
    result = run_tribunal_with_verdict(monkeypatch, finding, None)
    assert result.verified == "confirmed"
    assert "inconclusive" in result.verify_notes


def test_crew_convenes_tribunal_for_unrefuted_findings(monkeypatch):
    personas = load_builtin_personas(["mai-impatient-shopper"])
    convened = []

    async def fake_run_persona(persona, url, llm_factory, **kwargs):
        return PersonaResult(
            persona_name=persona.name, display_name=persona.display_name, ok=True,
            findings=[
                Finding(type="bug", severity="critical", title="ConfirmMe"),
                Finding(type="bug", severity="major", title="RefuteMe"),
            ],
        )

    async def fake_verify(finding, url, llm_factory, **kwargs):
        finding.verified = (
            "not_reproduced" if finding.title == "RefuteMe" else "confirmed"
        )
        return finding

    async def fake_probe(finding, url, llm_factory, **kwargs):
        return finding

    async def fake_tribunal(finding, url, provider, **kwargs):
        convened.append((finding.title, provider))
        return finding

    monkeypatch.setattr(crew_mod, "run_persona", fake_run_persona)
    monkeypatch.setattr(crew_mod, "verify_finding", fake_verify)
    monkeypatch.setattr(crew_mod, "cross_probe", fake_probe)
    monkeypatch.setattr(crew_mod, "tribunal_verify", fake_tribunal)

    asyncio.run(
        run_crew(
            personas, "https://example.com", llm_factory=lambda: None,
            verify=True, cross=True, tribunal=True, provider="openai",
        )
    )
    assert convened == [("ConfirmMe", "openai")]
