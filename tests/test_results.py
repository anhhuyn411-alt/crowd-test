import pytest

from crowdtest.results import (
    Finding,
    extract_report,
    parse_persona_report,
)

REPORT = '{"goal_achieved": true, "satisfaction_score": 8, "summary": "Nice.", "findings": []}'


def test_extract_bare_json():
    assert extract_report(REPORT)["satisfaction_score"] == 8


def test_extract_json_in_code_fence():
    text = f"Here is my report:\n```json\n{REPORT}\n```\nThanks!"
    assert extract_report(text)["goal_achieved"] is True


def test_extract_json_wrapped_in_prose():
    text = f"As Harold, I finished my session. {REPORT} That was my honest view."
    assert extract_report(text)["summary"] == "Nice."


def test_extract_rejects_garbage():
    with pytest.raises(ValueError):
        extract_report("I could not finish the task, sorry.")
    with pytest.raises(ValueError):
        extract_report(None)


def test_parse_report_coerces_bad_values():
    goal, score, summary, findings = parse_persona_report(
        {
            "goal_achieved": "yes",
            "satisfaction_score": 47,
            "summary": "  ok  ",
            "findings": [
                {"type": "explosion", "severity": "apocalyptic", "title": "Boom"},
                {"no_title": True},
                "not-a-dict",
            ],
        }
    )
    assert goal is True
    assert score == 10  # clamped
    assert summary == "ok"
    assert len(findings) == 1  # entries without a title are dropped
    assert findings[0].type == "ux"  # unknown type coerced
    assert findings[0].severity == "minor"  # unknown severity coerced


def test_finding_defaults():
    f = Finding(type="bug", severity="critical", title="It broke")
    assert f.where == ""
