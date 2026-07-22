"""Result types and the parser that extracts a report from an agent's final answer."""

from __future__ import annotations

import dataclasses
import json
import re

VALID_FINDING_TYPES = {"bug", "ux", "accessibility", "performance", "content"}
VALID_SEVERITIES = {"critical", "major", "minor"}


@dataclasses.dataclass
class Finding:
    type: str
    severity: str
    title: str
    description: str = ""
    where: str = ""

    def __post_init__(self) -> None:
        if self.type not in VALID_FINDING_TYPES:
            self.type = "ux"
        if self.severity not in VALID_SEVERITIES:
            self.severity = "minor"


@dataclasses.dataclass
class PersonaResult:
    persona_name: str
    display_name: str
    ok: bool
    goal_achieved: bool = False
    satisfaction_score: int | None = None
    summary: str = ""
    findings: list[Finding] = dataclasses.field(default_factory=list)
    steps: int | None = None
    duration_s: float | None = None
    error: str = ""


@dataclasses.dataclass
class CrewResult:
    url: str
    results: list[PersonaResult]

    @property
    def completed(self) -> list[PersonaResult]:
        return [r for r in self.results if r.ok]

    @property
    def all_findings(self) -> list[tuple[PersonaResult, Finding]]:
        return [(r, f) for r in self.completed for f in r.findings]

    @property
    def average_satisfaction(self) -> float | None:
        scores = [
            r.satisfaction_score
            for r in self.completed
            if r.satisfaction_score is not None
        ]
        if not scores:
            return None
        return sum(scores) / len(scores)

    def findings_by_severity(self) -> dict[str, int]:
        counts = {"critical": 0, "major": 0, "minor": 0}
        for _, f in self.all_findings:
            counts[f.severity] += 1
        return counts

    def survival_score(self) -> int | None:
        """0-100: how well the app survived the mob. None if nobody completed."""
        if not self.completed:
            return None
        counts = self.findings_by_severity()
        damage = 25 * counts["critical"] + 10 * counts["major"] + 3 * counts["minor"]
        score = 100 - damage
        avg = self.average_satisfaction
        if avg is not None:
            score = 0.7 * score + 0.3 * (avg * 10)
        return max(0, min(100, round(score)))

    def survival_grade(self) -> str | None:
        """Letter grade S/A/B/C/D/F derived from the survival score."""
        score = self.survival_score()
        if score is None:
            return None
        for threshold, grade in ((95, "S"), (85, "A"), (70, "B"), (55, "C"), (40, "D")):
            if score >= threshold:
                return grade
        return "F"


def extract_report(final_text: str | None) -> dict:
    """Pull the JSON report out of an agent's final message.

    Agents are told to answer with bare JSON, but models wrap it in prose or
    code fences often enough that we search for the outermost object instead
    of trusting the whole string.
    """
    if not final_text:
        raise ValueError("agent produced no final answer")

    fenced = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", final_text, re.DOTALL)
    candidates = [fenced.group(1)] if fenced else []

    start = final_text.find("{")
    end = final_text.rfind("}")
    if start != -1 and end > start:
        candidates.append(final_text[start : end + 1])

    for candidate in candidates:
        try:
            data = json.loads(candidate)
        except json.JSONDecodeError:
            continue
        if isinstance(data, dict):
            return data
    raise ValueError("no JSON report found in agent's final answer")


def parse_persona_report(data: dict) -> tuple[bool, int | None, str, list[Finding]]:
    """Validate and coerce a raw report dict into result fields."""
    goal_achieved = bool(data.get("goal_achieved", False))

    score = data.get("satisfaction_score")
    if isinstance(score, (int, float)):
        score = max(0, min(10, int(score)))
    else:
        score = None

    summary = str(data.get("summary", "")).strip()

    findings = []
    for raw in data.get("findings", []) or []:
        if not isinstance(raw, dict) or not raw.get("title"):
            continue
        findings.append(
            Finding(
                type=str(raw.get("type", "ux")),
                severity=str(raw.get("severity", "minor")),
                title=str(raw["title"]),
                description=str(raw.get("description", "")),
                where=str(raw.get("where", "")),
            )
        )
    return goal_achieved, score, summary, findings
