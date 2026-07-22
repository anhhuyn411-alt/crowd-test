from crowdtest.persona import generate_mob
from crowdtest.results import CrewResult, Finding, PersonaResult


def test_mob_generates_valid_unique_personas():
    mob = generate_mob(25, seed=42)
    assert len(mob) == 25
    assert len({p.name for p in mob}) == 25  # names unique
    for p in mob:
        assert p.goals
        prompt = p.to_task_prompt("https://example.com")
        assert "https://example.com" in prompt


def test_mob_is_reproducible_with_seed():
    a = generate_mob(10, seed=7)
    b = generate_mob(10, seed=7)
    assert [(p.display_name, p.age, p.goals) for p in a] == [
        (p.display_name, p.age, p.goals) for p in b
    ]
    c = generate_mob(10, seed=8)
    assert [p.age for p in a] != [p.age for p in c]


def make_crew(findings, scores):
    return CrewResult(
        url="https://example.com",
        results=[
            PersonaResult(
                persona_name=f"p{i}",
                display_name=f"P{i}",
                ok=True,
                satisfaction_score=s,
                findings=f,
            )
            for i, (f, s) in enumerate(zip(findings, scores))
        ],
    )


def test_survival_grade_clean_run_is_s():
    crew = make_crew([[], []], [10, 9])
    assert crew.survival_score() >= 95
    assert crew.survival_grade() == "S"


def test_survival_grade_degrades_with_findings():
    critical = Finding(type="bug", severity="critical", title="Broken checkout")
    crew = make_crew([[critical, critical], [critical]], [1, 2])
    assert crew.survival_grade() in ("D", "F")
    assert crew.survival_score() < 55


def test_survival_grade_none_when_all_failed():
    crew = CrewResult(
        url="https://example.com",
        results=[PersonaResult(persona_name="p", display_name="P", ok=False)],
    )
    assert crew.survival_score() is None
    assert crew.survival_grade() is None
