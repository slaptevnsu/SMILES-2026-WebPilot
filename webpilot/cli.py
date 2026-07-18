from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import cast

from webpilot.evaluator import WebPilotEvaluator
from webpilot.runner import WebPilotRunner
from webpilot.schemas import AgentVariant


AGENT_VARIANT_CHOICES = [
    "base",
    "deterministic-browser-feedback",
    "llm-code-only",
    "llm-browser-feedback",
]


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="webpilot",
        description="WebPilot MVP command line interface.",
    )

    subparsers = parser.add_subparsers(dest="command", required=True)

    run_parser = subparsers.add_parser(
        "run",
        help="Run WebPilot on a single task.",
    )
    run_parser.add_argument(
        "--task",
        required=True,
        type=Path,
        help="Path to a task JSON file.",
    )
    run_parser.add_argument(
        "--variant",
        default="base",
        choices=AGENT_VARIANT_CHOICES,
        help="Agent variant to run.",
    )
    run_parser.add_argument(
        "--max-iterations",
        type=int,
        default=None,
        help="Optional maximum number of repair iterations.",
    )

    evaluate_parser = subparsers.add_parser(
        "evaluate",
        help="Run evaluation over one or more tasks and variants.",
    )
    evaluate_parser.add_argument(
        "--tasks",
        required=True,
        nargs="+",
        type=Path,
        help="One or more task JSON files.",
    )
    evaluate_parser.add_argument(
        "--variants",
        nargs="+",
        choices=AGENT_VARIANT_CHOICES,
        default=None,
        help="Variants to evaluate. Defaults to base and deterministic-browser-feedback.",
    )

    return parser

def main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    if args.command == "run":
        runner = WebPilotRunner()
        summary = runner.run(
            task_path=args.task,
            variant=cast(AgentVariant, args.variant),
            max_iterations=args.max_iterations,
        )
        print(json.dumps(summary.model_dump(mode="json"), indent=2, ensure_ascii=False))
        return
    
    if args.command == "evaluate":
        variants = (
            [cast(AgentVariant, variant) for variant in args.variants]
            if args.variants is not None
            else None
        )

        summary = WebPilotEvaluator().evaluate(
            task_paths=args.tasks,
            variants=variants,
        )
        print(json.dumps(summary.model_dump(mode="json"), indent=2, ensure_ascii=False))
        return
    
    raise ValueError(f"Unknown command: {args.command}")


if __name__ == "__main__":
    main()