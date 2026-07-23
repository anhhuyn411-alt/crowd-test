"""crowd-test command line interface."""

from __future__ import annotations

import argparse
import asyncio
import dataclasses
import json
import os
import sys
from pathlib import Path

from crowdtest.crew import run_crew
from crowdtest.persona import generate_mob, load_builtin_personas, load_persona
from crowdtest.report import build_markdown, write_reports

DEFAULT_MODELS = {
    "anthropic": "claude-sonnet-5",
    "openai": "gpt-4o",
}


def make_llm_factory(provider: str, model: str | None):
    """Return a factory that builds a fresh LLM client per persona."""
    if provider == "auto":
        if os.environ.get("ANTHROPIC_API_KEY"):
            provider = "anthropic"
        elif os.environ.get("OPENAI_API_KEY"):
            provider = "openai"
        else:
            sys.exit(
                "No API key found. Set ANTHROPIC_API_KEY or OPENAI_API_KEY, "
                "or pass --provider explicitly."
            )

    chosen_model = model or DEFAULT_MODELS[provider]

    if provider == "anthropic":
        from browser_use.llm import ChatAnthropic

        return provider, chosen_model, lambda: ChatAnthropic(model=chosen_model)
    if provider == "openai":
        from browser_use.llm import ChatOpenAI

        return provider, chosen_model, lambda: ChatOpenAI(model=chosen_model)
    sys.exit(f"Unknown provider: {provider}")


def collect_personas(args: argparse.Namespace):
    personas = []
    if args.persona_file:
        personas.extend(load_persona(p) for p in args.persona_file)
    if args.personas == "all" and not args.persona_file and not args.mob:
        personas.extend(load_builtin_personas())
    elif args.personas not in ("all", "none"):
        names = [n.strip() for n in args.personas.split(",") if n.strip()]
        personas.extend(load_builtin_personas(names))
    if args.mob:
        personas.extend(generate_mob(args.mob, seed=args.seed))
    if not personas:
        sys.exit("No personas selected. Use --personas, --persona-file, or --mob N.")
    return personas


def cmd_run(args: argparse.Namespace) -> int:
    personas = collect_personas(args)
    provider, model, llm_factory = make_llm_factory(args.provider, args.model)

    print(f"crowd-test: sending {len(personas)} virtual users to {args.url}")
    print(f"  provider={provider} model={model} "
          f"concurrency={args.concurrency} max_steps={args.max_steps}")
    for p in personas:
        print(f"  - {p.display_name}")
    print()

    def on_progress(name: str, status: str) -> None:
        print(f"  [{status}] {name}")

    crew = asyncio.run(
        run_crew(
            personas,
            args.url,
            llm_factory,
            extra_goal=args.goal,
            headless=not args.headed,
            max_steps=args.max_steps,
            concurrency=args.concurrency,
            verify=args.verify or args.cross_verify or args.tribunal,
            cross=args.cross_verify or args.tribunal,
            tribunal=args.tribunal,
            provider=provider,
            on_progress=on_progress,
        )
    )

    # Reports hit the disk before anything else touches stdout: a console
    # that chokes on emoji must never cost the user their run.
    md_path, html_path = write_reports(crew, args.out)
    json_path = Path(args.out) / "results.json"
    json_path.write_text(
        json.dumps(dataclasses.asdict(crew), indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    print()
    print(build_markdown(crew))
    print(f"\nReports written:\n  {md_path}\n  {html_path}\n  {json_path}")

    counts = crew.findings_by_severity()
    if args.fail_on_critical and counts["critical"] > 0:
        return 2
    return 0 if crew.completed else 1


def cmd_list_personas(_args: argparse.Namespace) -> int:
    for p in load_builtin_personas():
        levels = f"tech={p.tech_savviness}, patience={p.patience}, device={p.device}"
        print(f"{p.name:24} {p.display_name} ({levels})")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="crowd-test",
        description="Hire a crowd of AI virtual users to test your web app.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    run = sub.add_parser("run", help="send the crowd to a URL")
    run.add_argument("url", help="the website to test")
    run.add_argument(
        "--personas",
        default="all",
        help='comma-separated built-in persona names, "all" (default), or "none"',
    )
    run.add_argument(
        "--mob",
        type=int,
        metavar="N",
        help="unleash N randomly generated virtual users on top of the selection",
    )
    run.add_argument(
        "--seed",
        type=int,
        help="random seed for --mob, to make a mob reproducible",
    )
    run.add_argument(
        "--persona-file",
        action="append",
        type=Path,
        default=[],
        help="path to a custom persona YAML (repeatable)",
    )
    run.add_argument("--goal", help="extra mission given to every persona")
    run.add_argument(
        "--provider",
        choices=["auto", "anthropic", "openai"],
        default="auto",
        help="LLM provider (default: auto-detect from env keys)",
    )
    run.add_argument("--model", help="model id override")
    run.add_argument("--concurrency", type=int, default=3,
                     help="personas browsing at once (default 3)")
    run.add_argument("--max-steps", type=int, default=25,
                     help="max browser actions per persona (default 25)")
    run.add_argument("--verify", action="store_true",
                     help="send an independent detective agent to reproduce every "
                          "critical/major finding; refuted ones stop counting "
                          "toward the survival grade")
    run.add_argument("--cross-verify", action="store_true",
                     help="like --verify, plus re-check confirmed findings in a "
                          "second independent browser engine (Playwright); needs "
                          "pip install crowd-test[probe]")
    run.add_argument("--tribunal", action="store_true",
                     help="convene the full tribunal: detective + Playwright "
                          "probe + a Microsoft Webwright agent (third harness); "
                          "implies --verify and --cross-verify, needs "
                          "pip install git+https://github.com/microsoft/Webwright")
    run.add_argument("--headed", action="store_true",
                     help="show browser windows instead of headless")
    run.add_argument("--out", default="crowd-test-reports",
                     help="output directory for reports")
    run.add_argument("--fail-on-critical", action="store_true",
                     help="exit code 2 if any critical finding (for CI)")
    run.set_defaults(func=cmd_run)

    lst = sub.add_parser("list-personas", help="show built-in personas")
    lst.set_defaults(func=cmd_list_personas)
    return parser


def main() -> None:
    # Windows consoles and redirected stdout often default to a legacy
    # codepage that can't print the report's emoji; degrade gracefully
    # instead of dying with UnicodeEncodeError.
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            try:
                stream.reconfigure(encoding="utf-8", errors="replace")
            except Exception:
                pass
    args = build_parser().parse_args()
    sys.exit(args.func(args))


if __name__ == "__main__":
    main()
