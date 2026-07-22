import pytest

from crowdtest.persona import Persona, load_builtin_personas, load_persona


def test_builtin_personas_load_and_validate():
    personas = load_builtin_personas()
    assert len(personas) == 10
    names = {p.name for p in personas}
    assert "rex-chaos-monkey" in names
    assert "harold-the-senior" in names
    assert "viktor-privacy-hawk" in names
    assert "sam-speedrunner" in names


def test_load_builtin_subset_and_unknown():
    subset = load_builtin_personas(["mai-impatient-shopper"])
    assert len(subset) == 1
    with pytest.raises(KeyError):
        load_builtin_personas(["nobody-here"])


def test_task_prompt_contains_identity_goals_and_url():
    persona = load_builtin_personas(["harold-the-senior"])[0]
    prompt = persona.to_task_prompt("https://example.com", extra_goal="Buy socks")
    assert "https://example.com" in prompt
    assert "Harold" in prompt
    assert "Buy socks" in prompt
    for goal in persona.goals:
        assert goal in prompt
    assert '"satisfaction_score"' in prompt


def test_invalid_levels_rejected():
    with pytest.raises(ValueError):
        Persona(
            name="x", display_name="X", age=30,
            tech_savviness="extreme", patience="medium", goals=["g"],
        )
    with pytest.raises(ValueError):
        Persona(
            name="x", display_name="X", age=30,
            tech_savviness="medium", patience="medium", goals=[],
        )


def test_load_persona_rejects_unknown_fields(tmp_path):
    bad = tmp_path / "bad.yaml"
    bad.write_text(
        "name: a\ndisplay_name: A\nage: 20\ntech_savviness: low\n"
        "patience: low\ngoals: [g]\nsuperpower: flight\n",
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="superpower"):
        load_persona(bad)
