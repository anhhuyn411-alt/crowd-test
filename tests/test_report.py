from crowdtest.report import build_html, build_markdown, write_reports
from crowdtest.results import CrewResult, Finding, PersonaResult


def sample_crew() -> CrewResult:
    return CrewResult(
        url="https://example.com",
        results=[
            PersonaResult(
                persona_name="mai-impatient-shopper",
                display_name="Mai — The Impatient Shopper",
                ok=True,
                goal_achieved=False,
                satisfaction_score=3,
                summary="Checkout wanted my life story. I left.",
                findings=[
                    Finding(
                        type="ux", severity="critical",
                        title="Checkout requires account creation",
                        description="No guest checkout; I abandoned my cart.",
                        where="Checkout step 1",
                    ),
                    Finding(type="performance", severity="minor",
                            title="Slow product images"),
                ],
                steps=14,
                duration_s=88.0,
            ),
            PersonaResult(
                persona_name="harold-the-senior",
                display_name="Harold — The Senior Citizen",
                ok=False,
                error="RuntimeError: browser crashed",
            ),
        ],
    )


def test_markdown_report_contents():
    md = build_markdown(sample_crew(), generated_at="2026-07-22")
    assert "https://example.com" in md
    assert "Checkout requires account creation" in md
    assert "Mai — The Impatient Shopper" in md
    assert "1 critical / 0 major / 1 minor" in md
    assert "session failed" in md  # Harold's crash is visible, not hidden


def test_html_report_contents_and_escaping():
    crew = sample_crew()
    crew.results[0].summary = 'I typed <script>alert("x")</script> into search.'
    html = build_html(crew, generated_at="2026-07-22")
    assert "crowd-test report" in html
    assert "Checkout requires account creation" in html
    assert "<script>alert" not in html  # jinja autoescape on
    assert "&lt;script&gt;" in html


def test_write_reports(tmp_path):
    md, html = write_reports(sample_crew(), tmp_path / "out")
    assert md.exists() and html.exists()
    assert md.read_text(encoding="utf-8").startswith("# crowd-test report")


def test_average_satisfaction_ignores_failures():
    crew = sample_crew()
    assert crew.average_satisfaction == 3.0
    assert crew.findings_by_severity() == {"critical": 1, "major": 0, "minor": 1}
