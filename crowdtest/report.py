"""Turn a CrewResult into shareable Markdown and HTML reports."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from jinja2 import Environment, BaseLoader

from crowdtest.results import CrewResult

SEVERITY_ORDER = {"critical": 0, "major": 1, "minor": 2}
SEVERITY_EMOJI = {"critical": "🔴", "major": "🟠", "minor": "🟡"}

GRADE_VERDICTS = {
    "S": "the mob couldn't lay a finger on it",
    "A": "survived with a few scratches",
    "B": "walked away limping",
    "C": "took real damage",
    "D": "barely crawled out alive",
    "F": "☠️ the mob destroyed it",
}


def build_markdown(crew: CrewResult, generated_at: str | None = None) -> str:
    """Plain-Markdown report, good for terminals and PR comments."""
    ts = generated_at or datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    counts = crew.findings_by_severity()
    avg = crew.average_satisfaction
    avg_text = f"{avg:.1f}/10" if avg is not None else "n/a"

    lines = [
        f"# crowd-test report — {crew.url}",
        "",
        f"*Generated {ts} by [crowd-test](https://github.com/anhhuyn411-alt/crowd-test)*",
        "",
        "## Verdict",
        "",
        (
            f"**🏆 Survival grade: {crew.survival_grade()} "
            f"({crew.survival_score()}/100)** — {GRADE_VERDICTS[crew.survival_grade()]}"
            if crew.survival_grade()
            else "**Survival grade: n/a** — no persona completed their session"
        ),
        "",
        f"- **Virtual users:** {len(crew.results)} sent, {len(crew.completed)} completed",
        f"- **Average satisfaction:** {avg_text}",
        f"- **Findings:** {counts['critical']} critical / {counts['major']} major / {counts['minor']} minor",
        "",
    ]

    findings = sorted(
        crew.all_findings, key=lambda pair: SEVERITY_ORDER[pair[1].severity]
    )
    if findings:
        lines += ["## Findings", ""]
        for result, f in findings:
            emoji = SEVERITY_EMOJI[f.severity]
            badge = ""
            if f.verified == "confirmed":
                badge = " ✅ *verified by detective*"
            elif f.verified == "not_reproduced":
                badge = " ⚠️ *could not be reproduced — excluded from grade*"
            elif f.verified == "disputed":
                badge = (
                    " 🔬 *disputed by cross-engine probe — likely automation "
                    "artifact, excluded from grade*"
                )
            lines.append(
                f"- {emoji} **[{f.severity}/{f.type}] {f.title}**{badge}"
                f" — {f.description} _(found by {result.display_name}"
                + (f", at: {f.where}" if f.where else "")
                + ")_"
                + (f" — detective: {f.verify_notes}" if f.verify_notes else "")
            )
        lines.append("")
    else:
        lines += ["## Findings", "", "No findings — the crowd had a smooth ride. 🎉", ""]

    lines += ["## The crowd", ""]
    for r in crew.results:
        if r.ok:
            score = (
                f"{r.satisfaction_score}/10"
                if r.satisfaction_score is not None
                else "n/a"
            )
            goal = "achieved their goal" if r.goal_achieved else "gave up on their goal"
            lines += [
                f"### {r.display_name} — {score}, {goal}",
                "",
                f"> {r.summary}" if r.summary else "> (no summary)",
                "",
            ]
        else:
            lines += [
                f"### {r.display_name} — session failed",
                "",
                f"`{short_error(r.error)}`",
                "",
            ]
    return "\n".join(lines)


def short_error(error: str) -> str:
    """Condense a traceback to its final meaningful line for the report."""
    lines = [line.strip() for line in (error or "").strip().splitlines()]
    lines = [line for line in lines if line]
    return lines[-1] if lines else "unknown error"


HTML_TEMPLATE = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>crowd-test — {{ crew.url }}</title>
<style>
  :root { --bg:#0f1117; --card:#1a1d27; --text:#e6e8ee; --muted:#9aa0b0;
          --critical:#ff5470; --major:#ffb454; --minor:#ffe27a; --ok:#3ddc97; }
  * { box-sizing:border-box; margin:0; }
  body { font-family:system-ui,-apple-system,"Segoe UI",sans-serif; background:var(--bg);
         color:var(--text); line-height:1.6; padding:2.5rem 1rem; }
  .wrap { max-width:860px; margin:0 auto; }
  h1 { font-size:1.5rem; margin-bottom:.25rem; }
  .sub { color:var(--muted); margin-bottom:2rem; font-size:.9rem; }
  .tiles { display:grid; grid-template-columns:repeat(auto-fit,minmax(160px,1fr));
           gap:.75rem; margin-bottom:2rem; }
  .tile { background:var(--card); border-radius:12px; padding:1rem 1.25rem; }
  .tile b { display:block; font-size:1.6rem; }
  .tile span { color:var(--muted); font-size:.8rem; }
  h2 { font-size:1.1rem; margin:2rem 0 .75rem; }
  .finding { background:var(--card); border-radius:12px; padding:.9rem 1.1rem;
             margin-bottom:.6rem; border-left:4px solid var(--minor); }
  .finding.critical { border-color:var(--critical); }
  .finding.major { border-color:var(--major); }
  .finding .meta { color:var(--muted); font-size:.78rem; text-transform:uppercase;
                   letter-spacing:.05em; }
  .persona { background:var(--card); border-radius:12px; padding:1.1rem 1.25rem;
             margin-bottom:.75rem; }
  .persona .score { float:right; font-weight:700; }
  .persona .score.good { color:var(--ok); }
  .persona .score.bad { color:var(--critical); }
  .persona blockquote { color:var(--muted); font-style:italic; margin-top:.4rem;
                        border-left:3px solid #333a4d; padding-left:.75rem; }
  .error { color:var(--critical); font-family:monospace; font-size:.8rem;
           white-space:pre-wrap; }
  footer { color:var(--muted); font-size:.8rem; margin-top:2.5rem; text-align:center; }
  a { color:#7aa2ff; }
</style>
</head>
<body>
<div class="wrap">
  <h1>crowd-test report</h1>
  <div class="sub">{{ crew.url }} &middot; generated {{ generated_at }}</div>

  <div class="tiles">
    <div class="tile"><b>{{ grade if grade else '–' }}</b><span>survival grade{% if score is not none %} · {{ score }}/100{% endif %}</span></div>
    <div class="tile"><b>{{ crew.results|length }}</b><span>virtual users sent</span></div>
    <div class="tile"><b>{{ avg_text }}</b><span>avg. satisfaction</span></div>
    <div class="tile"><b>{{ counts.critical }}</b><span>critical findings</span></div>
    <div class="tile"><b>{{ counts.major }}</b><span>major findings</span></div>
    <div class="tile"><b>{{ counts.minor }}</b><span>minor findings</span></div>
  </div>

  <h2>Findings</h2>
  {% if findings %}
    {% for result, f in findings %}
    <div class="finding {{ f.severity }}">
      <div class="meta">{{ f.severity }} &middot; {{ f.type }}
        {% if f.where %} &middot; {{ f.where }}{% endif %}
        {% if f.verified == 'confirmed' %} &middot; ✅ verified{% elif f.verified == 'not_reproduced' %} &middot; ⚠️ not reproduced — excluded from grade{% elif f.verified == 'disputed' %} &middot; 🔬 disputed by cross-engine probe — excluded from grade{% endif %}</div>
      <strong>{{ f.title }}</strong>
      <div>{{ f.description }}</div>
      {% if f.verify_notes %}<div class="meta" style="margin-top:.3rem">detective: {{ f.verify_notes }}</div>{% endif %}
      <div class="meta" style="margin-top:.3rem">found by {{ result.display_name }}</div>
    </div>
    {% endfor %}
  {% else %}
    <p>No findings &mdash; the crowd had a smooth ride. 🎉</p>
  {% endif %}

  <h2>The crowd</h2>
  {% for r in crew.results %}
  <div class="persona">
    {% if r.ok %}
      <span class="score {{ 'good' if (r.satisfaction_score or 0) >= 7 else ('bad' if (r.satisfaction_score or 0) <= 4 else '') }}">
        {{ r.satisfaction_score if r.satisfaction_score is not none else '&ndash;' }}/10</span>
      <strong>{{ r.display_name }}</strong>
      <div class="sub" style="margin:0">
        {{ 'achieved their goal' if r.goal_achieved else 'gave up on their goal' }}{% if r.duration_s %} &middot; {{ r.duration_s }}s{% endif %}{% if r.steps %} &middot; {{ r.steps }} steps{% endif %}
      </div>
      {% if r.summary %}<blockquote>&ldquo;{{ r.summary }}&rdquo;</blockquote>{% endif %}
    {% else %}
      <strong>{{ r.display_name }}</strong> &mdash; session failed
      <div class="error">{{ short_error(r.error) }}</div>
    {% endif %}
  </div>
  {% endfor %}

  <footer>made with <a href="https://github.com/anhhuyn411-alt/crowd-test">crowd-test</a>
    &mdash; hire a crowd of AI users to test your app</footer>
</div>
</body>
</html>
"""


def build_html(crew: CrewResult, generated_at: str | None = None) -> str:
    """Self-contained dark-theme HTML report, the shareable artifact."""
    ts = generated_at or datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    avg = crew.average_satisfaction
    env = Environment(loader=BaseLoader(), autoescape=True)
    template = env.from_string(HTML_TEMPLATE)
    findings = sorted(
        crew.all_findings, key=lambda pair: SEVERITY_ORDER[pair[1].severity]
    )
    return template.render(
        crew=crew,
        generated_at=ts,
        counts=crew.findings_by_severity(),
        avg_text=f"{avg:.1f}" if avg is not None else "–",
        findings=findings,
        grade=crew.survival_grade(),
        score=crew.survival_score(),
        short_error=short_error,
    )


def write_reports(crew: CrewResult, out_dir: str | Path) -> tuple[Path, Path]:
    """Write report.md and report.html into *out_dir*; returns both paths."""
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    md_path = out / "report.md"
    html_path = out / "report.html"
    md_path.write_text(build_markdown(crew), encoding="utf-8")
    html_path.write_text(build_html(crew), encoding="utf-8")
    return md_path, html_path
