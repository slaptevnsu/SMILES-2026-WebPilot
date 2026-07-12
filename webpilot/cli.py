from __future__ import annotations

import argparse
import json
from pathlib import Path

from webpilot.runner import WebPilotRunner
from webpilot.schemas import AgentVariant


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="webpilot",
        description="WebPilot MVP CLI"
    )

    subparsers = parser.add_subparsers(dest="command", required=True)

    run_parser = subparsers.add_parser("run", help="Run a WebPilot task")
    run_parser.add_argument(
        "--task",
        required=True,
        type=Path,
        help="Path to a task JSON file",
    )
    run_parser.add_argument(
        "--variant",
        default="base",
        choices=["base", "browser-feedback"],
        help="Agent variant to run",
    )
    run_parser.add_argument(
        "--max-iterations",
        type=int,
        default=None,
        help="Override max_iterations from the task file",
    )

    return parser

def main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    if args.command == "run":
        runner = WebPilotRunner()
        summary = runner.run(
            task_path=args.task,
            variant=args.variant,
            max_iterations=args.max_iterations,
        )
        print(json.dumps(summary.model_dump(mode="json"), indent=2, ensure_ascii=False))
        return

    raise ValueError(f"Unknown command: {args.command}")


if __name__ == "__main__":
    main()