"""Third-opinion verification: re-run a finding through Microsoft Webwright.

The verification ladder so far: the detective (--verify) drives the same
browser-use stack as the mob, the probe (--cross-verify) executes a declarative
script in raw Playwright. Webwright is a third, architecturally different
harness — a coding agent that writes and debugs its own Playwright scripts in a
throwaway workspace. It fails in different ways than both stacks above, which
is exactly what a last court of appeal is for.

Webwright is not on PyPI under its own name (the "webwright" package there is
an unrelated project), so it stays a soft dependency:

    pip install git+https://github.com/microsoft/Webwright

Verdict semantics mirror the probe: the tribunal can dispute a finding that
nothing else has positively reproduced, and records a dissent when earlier
engines disagree — it never silently overrules a reproduction.
"""

from __future__ import annotations

import asyncio
import importlib.util
import json
import re
import subprocess
import sys
import tempfile
from pathlib import Path

from crowdtest.results import Finding

TRIBUNAL_TIMEOUT_S = 600

TRIBUNAL_TASK = """You are a skeptical QA engineer. A tester reported a bug on {url} and your
job is to find out whether it is real, by reproducing it yourself.

The bug report:
- Title: {title}
- Where: {where}
- Description: {description}

Follow the reported steps faithfully (use any credentials mentioned in the
report). Retry once on a fresh page before concluding the bug is real.

When you are done, write a file named verdict.json in your workspace directory
containing exactly one JSON object:

{{"bug_present": true or false, "notes": "one sentence of evidence"}}

Writing verdict.json is mandatory — it is how your verdict is collected.
"""


def webwright_available() -> bool:
    """True when Microsoft's Webwright (webwright.run.cli) is importable."""
    try:
        return importlib.util.find_spec("webwright.run.cli") is not None
    except (ImportError, ModuleNotFoundError, ValueError):
        return False


def config_for_provider(provider: str) -> str:
    """Map a crowd-test provider name onto a Webwright model config."""
    return "model_claude.yaml" if provider == "anthropic" else "model_openai.yaml"


def _load_json_object(text: str) -> dict | None:
    try:
        data = json.loads(text)
    except (json.JSONDecodeError, ValueError):
        return None
    return data if isinstance(data, dict) else None


def find_verdict(output_dir: Path) -> dict | None:
    """Locate the agent's verdict in Webwright's run artifacts.

    Preferred: a verdict.json the agent was told to write. Fallback: scan the
    run artifacts for an inline {"bug_present": ...} object, because the agent
    may state its verdict in the trajectory instead of (or before) writing the
    file. Newest files win in both passes.
    """
    by_mtime = lambda p: p.stat().st_mtime  # noqa: E731

    for path in sorted(output_dir.rglob("verdict.json"), key=by_mtime, reverse=True):
        data = _load_json_object(path.read_text(encoding="utf-8", errors="replace"))
        if data is not None and "bug_present" in data:
            return data

    candidates = [
        p
        for pattern in ("*.json", "*.jsonl", "*.md", "*.txt", "*.log")
        for p in output_dir.rglob(pattern)
    ]
    for path in sorted(set(candidates), key=by_mtime, reverse=True):
        text = path.read_text(encoding="utf-8", errors="replace")
        for match in re.finditer(r'\{[^{}]*"bug_present"[^{}]*\}', text):
            data = _load_json_object(match.group(0).replace('\\"', '"'))
            if data is not None and "bug_present" in data:
                return data
    return None


def _run_webwright(task: str, provider: str, output_dir: Path) -> None:
    subprocess.run(
        [
            sys.executable,
            "-m",
            "webwright.run.cli",
            "-c",
            "base.yaml",
            "-c",
            config_for_provider(provider),
            "-t",
            task,
            "--task-id",
            "crowdtest-tribunal",
            "-o",
            str(output_dir),
        ],
        capture_output=True,
        timeout=TRIBUNAL_TIMEOUT_S,
        check=False,
    )


def _positively_reproduced(finding: Finding) -> bool:
    return finding.verified == "confirmed" or "reproduced" in finding.verify_notes


async def tribunal_verify(
    finding: Finding, url: str, provider: str, *, headless: bool = True
) -> Finding:
    """Last court of appeal: an independent Webwright agent retries the repro.

    Always headless — Webwright's headed mode is interactive-debug only.
    """
    if not webwright_available():
        finding.verify_notes += (
            " | tribunal skipped: install Webwright with "
            "pip install git+https://github.com/microsoft/Webwright"
        )
        return finding

    task = TRIBUNAL_TASK.format(
        url=url,
        title=finding.title,
        where=finding.where or "(not specified)",
        description=finding.description or finding.title,
    )
    output_dir = Path(tempfile.mkdtemp(prefix="crowdtest-tribunal-"))
    try:
        await asyncio.to_thread(_run_webwright, task, provider, output_dir)
        verdict = find_verdict(output_dir)
    except Exception as exc:  # best-effort, like the probe
        finding.verify_notes += f" | tribunal errored ({type(exc).__name__})"
        return finding

    if verdict is None:
        finding.verify_notes += " | tribunal inconclusive (agent left no verdict)"
    elif verdict.get("bug_present"):
        finding.verify_notes += " | tribunal (Webwright): reproduced independently"
        if finding.verified == "":
            finding.verified = "confirmed"
    elif _positively_reproduced(finding):
        # Another engine actually reproduced it; record the dissent instead of
        # letting the newest opinion silently win.
        finding.verify_notes += (
            " | tribunal (Webwright) dissents: could not reproduce"
        )
    else:
        finding.verified = "disputed"
        finding.verify_notes += (
            " | tribunal (Webwright): could not reproduce in a third harness — "
            "excluded from grade"
        )
    return finding
