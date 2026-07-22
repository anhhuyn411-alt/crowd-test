"""Persona definitions: who the virtual users are and how they behave."""

from __future__ import annotations

import dataclasses
from importlib import resources
from pathlib import Path

import yaml

VALID_LEVELS = {"very_low", "low", "medium", "high", "very_high"}

PATIENCE_RULES = {
    "very_low": (
        "You are extremely impatient. If a page is confusing, slow, or a flow takes "
        "more than a few steps, you get frustrated fast and consider abandoning it. "
        "Record WHY you wanted to leave."
    ),
    "low": (
        "You have little patience. You skim instead of reading, and you give any "
        "confusing screen only one retry before frustration kicks in."
    ),
    "medium": "You have average patience. You tolerate small annoyances but note them.",
    "high": "You are patient and willing to read instructions and retry a few times.",
    "very_high": (
        "You are exceptionally patient and methodical. You explore thoroughly and "
        "read everything before acting."
    ),
}

TECH_RULES = {
    "very_low": (
        "You barely understand technology. Icons without labels confuse you. You do "
        "not know conventions like hamburger menus, and you often misread UI elements. "
        "Behave accordingly and record every moment of confusion."
    ),
    "low": (
        "You are not tech-savvy. You only recognize very common patterns (a cart "
        "icon, a search box) and get lost outside them."
    ),
    "medium": "You have ordinary consumer-level tech skills.",
    "high": "You are tech-savvy, move fast, and recognize common UI patterns instantly.",
    "very_high": (
        "You are a power user. You use search, shortcuts, and direct navigation, and "
        "you notice sloppy engineering details other users would miss."
    ),
}


@dataclasses.dataclass
class Persona:
    """One virtual user: identity, skill profile, mission, and quirks."""

    name: str
    display_name: str
    age: int
    tech_savviness: str
    patience: str
    device: str = "desktop"
    background: str = ""
    goals: list[str] = dataclasses.field(default_factory=list)
    traits: list[str] = dataclasses.field(default_factory=list)
    quirks: list[str] = dataclasses.field(default_factory=list)

    def __post_init__(self) -> None:
        if not self.name:
            raise ValueError("persona needs a non-empty 'name'")
        if self.tech_savviness not in VALID_LEVELS:
            raise ValueError(
                f"persona '{self.name}': tech_savviness must be one of {sorted(VALID_LEVELS)}"
            )
        if self.patience not in VALID_LEVELS:
            raise ValueError(
                f"persona '{self.name}': patience must be one of {sorted(VALID_LEVELS)}"
            )
        if not self.goals:
            raise ValueError(f"persona '{self.name}' needs at least one goal")

    def to_task_prompt(self, url: str, extra_goal: str | None = None) -> str:
        """Compile this persona into the browser agent's task prompt."""
        goals = list(self.goals)
        if extra_goal:
            goals.insert(0, extra_goal)
        goal_lines = "\n".join(f"- {g}" for g in goals)
        trait_lines = "\n".join(f"- {t}" for t in self.traits) or "- (none)"
        quirk_lines = "\n".join(f"- {q}" for q in self.quirks) or "- (none)"

        return f"""You are role-playing a REAL human user testing a website. Stay in character the whole session.

## Who you are
{self.display_name}, {self.age} years old. {self.background}

## How you behave
{TECH_RULES[self.tech_savviness]}
{PATIENCE_RULES[self.patience]}

Personality traits:
{trait_lines}

Behavioral quirks (act these out when the situation fits):
{quirk_lines}

## Your mission
Open {url} and, as this person, try to:
{goal_lines}

While using the site, mentally note every problem you hit: broken features, confusing
layouts, missing labels, slow or dead interactions, anything that makes you struggle.

## Final report (IMPORTANT)
When you finish (or give up), your VERY LAST message must be ONLY a JSON object,
no prose around it, in exactly this shape:

{{
  "goal_achieved": true,
  "satisfaction_score": 7,
  "summary": "One short paragraph, in character, about how the session felt.",
  "findings": [
    {{
      "type": "bug",
      "severity": "major",
      "title": "Short title",
      "description": "What happened and why it hurt you as this user.",
      "where": "Page or element where it happened"
    }}
  ]
}}

Rules for the report:
- "type" is one of: "bug", "ux", "accessibility", "performance", "content".
- "severity" is one of: "critical", "major", "minor".
- "satisfaction_score" is an integer 0-10 for how the session felt to THIS persona.
- An empty "findings" list is a valid answer if the site genuinely gave you no trouble.
"""


def load_persona(path: str | Path) -> Persona:
    """Load a single persona from a YAML file."""
    raw = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValueError(f"{path}: persona YAML must be a mapping")
    known = {f.name for f in dataclasses.fields(Persona)}
    unknown = set(raw) - known
    if unknown:
        raise ValueError(f"{path}: unknown persona fields {sorted(unknown)}")
    return Persona(**raw)


def builtin_persona_dir() -> Path:
    """Directory holding the personas shipped with the package."""
    return Path(resources.files("crowdtest")) / "personas"


def load_builtin_personas(names: list[str] | None = None) -> list[Persona]:
    """Load built-in personas; all of them when *names* is None."""
    directory = builtin_persona_dir()
    personas = [load_persona(p) for p in sorted(directory.glob("*.yaml"))]
    if names is None:
        return personas
    by_name = {p.name: p for p in personas}
    missing = [n for n in names if n not in by_name]
    if missing:
        raise KeyError(
            f"unknown persona(s) {missing}; available: {sorted(by_name)}"
        )
    return [by_name[n] for n in names]
