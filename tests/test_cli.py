import json
from pathlib import Path

import pytest

import webpilot.cli as cli
from webpilot.schemas import EvaluationSummary, RunSummary


def test_build_parser_parses_run_command() -> None:
    parser = cli.build_parser()

    args = parser.parse_args(
        [
            "run",
            "--task",
            "tasks/sample_text_generation.json",
            "--variant",
            "base",
            "--max-iterations",
            "2",
        ]
    )

    assert args.command == "run"
    assert args.task == Path("tasks/sample_text_generation.json")
    assert args.variant == "base"
    assert args.max_iterations == 2


def test_build_parser_rejects_unknown_variant() -> None:
    parser = cli.build_parser()

    with pytest.raises(SystemExit):
        parser.parse_args(
            [
                "run",
                "--task",
                "tasks/sample_text_generation.json",
                "--variant",
                "unknown-variant",
            ]
        )


def test_main_run_prints_runner_summary(monkeypatch, capsys) -> None:
    calls = {}

    class FakeRunner:
        def run(self, *, task_path: Path, variant: str, max_iterations: int | None) -> RunSummary:
            calls["task_path"] = task_path
            calls["variant"] = variant
            calls["max_iterations"] = max_iterations

            return RunSummary(
                task_id="sample_cli_task",
                task_type="text_generation",
                variant="base",
                status="generated_and_verified",
                run_dir="outputs/sample_cli_task/run",
                message="ok",
            )

    monkeypatch.setattr(cli, "WebPilotRunner", FakeRunner)
    monkeypatch.setattr(
        "sys.argv",
        [
            "webpilot",
            "run",
            "--task",
            "tasks/sample_text_generation.json",
            "--variant",
            "base",
            "--max-iterations",
            "2",
        ],
    )

    cli.main()

    assert calls["task_path"] == Path("tasks/sample_text_generation.json")
    assert calls["variant"] == "base"
    assert calls["max_iterations"] == 2

    output = json.loads(capsys.readouterr().out)

    assert output["task_id"] == "sample_cli_task"
    assert output["task_type"] == "text_generation"
    assert output["variant"] == "base"
    assert output["status"] == "generated_and_verified"


def test_main_evaluate_prints_evaluator_summary(monkeypatch, capsys, tmp_path: Path) -> None:
    calls = {}

    class FakeEvaluator:
        def evaluate(
            self,
            *,
            task_paths: list[Path],
            variants: list[str] | None,
        ) -> EvaluationSummary:
            calls["task_paths"] = task_paths
            calls["variants"] = variants

            return EvaluationSummary(
                evaluation_id="test_eval",
                output_dir=str(tmp_path / "outputs" / "evaluations" / "test_eval"),
                total_runs=0,
                passed_runs=0,
                failed_runs=0,
                repaired_runs=0,
                records=[],
            )

    monkeypatch.setattr(cli, "WebPilotEvaluator", FakeEvaluator)
    monkeypatch.setattr(
        "sys.argv",
        [
            "webpilot",
            "evaluate",
            "--tasks",
            "tasks/sample_nav_repair.json",
            "tasks/sample_tabs_repair.json",
            "--variants",
            "base",
            "llm-browser-feedback",
        ],
    )

    cli.main()

    assert calls["task_paths"] == [
        Path("tasks/sample_nav_repair.json"),
        Path("tasks/sample_tabs_repair.json"),
    ]
    assert calls["variants"] == ["base", "llm-browser-feedback"]

    output = json.loads(capsys.readouterr().out)

    assert output["evaluation_id"] == "test_eval"
    assert output["total_runs"] == 0
    assert output["records"] == []
