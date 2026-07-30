import json
from pathlib import Path

import pytest

from webpilot.project_edit import (
    AppliedFileChange,
    FileChange,
    apply_file_changes,
    extract_file_changes,
    parse_llm_json_response,
    write_changed_files_artifact,
    write_project_patch,
)


def test_parse_llm_json_response_accepts_plain_json() -> None:
    parsed = parse_llm_json_response('{"changes": [], "rationale": "ok"}')

    assert parsed == {"changes": [], "rationale": "ok"}


def test_parse_llm_json_response_accepts_fenced_json() -> None:
    raw_response = (
        "```json\n"
        '{"changes": [{"path": "src/App.jsx", '
        '"content": "export default function App() { return null; }"}]}\n'
        "```"
    )

    parsed = parse_llm_json_response(raw_response)

    assert parsed["changes"][0]["path"] == "src/App.jsx"


def test_parse_llm_json_response_rejects_non_object() -> None:
    with pytest.raises(ValueError, match="LLM response must be a JSON object"):
        parse_llm_json_response('["not", "an", "object"]')


def test_extract_file_changes_validates_changes_shape() -> None:
    with pytest.raises(ValueError, match="list field named 'changes'"):
        extract_file_changes({"files": []})

    with pytest.raises(ValueError, match="Change at index 0 must be an object"):
        extract_file_changes({"changes": ["bad"]})

    with pytest.raises(ValueError, match="non-string path"):
        extract_file_changes({"changes": [{"path": 123, "content": "ok"}]})

    with pytest.raises(ValueError, match="non-string content"):
        extract_file_changes({"changes": [{"path": "src/App.jsx", "content": 123}]})


def test_extract_file_changes_normalizes_content_newline() -> None:
    changes = extract_file_changes(
        {
            "changes": [
                {
                    "path": "src/App.jsx",
                    "content": "export default function App() { return null; }",
                }
            ]
        }
    )

    assert len(changes) == 1
    assert changes[0].path == "src/App.jsx"
    assert changes[0].content.endswith("\n")


def test_apply_file_changes_modifies_existing_file(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    app = repo / "src" / "App.jsx"
    app.parent.mkdir(parents=True)

    before = "export default function App() { return <p>Old</p>; }\n"
    after = "export default function App() { return <p>New</p>; }\n"
    app.write_text(before, encoding="utf-8")

    applied = apply_file_changes(
        repo_path=repo,
        before_by_path={"src/App.jsx": before},
        changes=[FileChange(path="src/App.jsx", content=after)],
    )

    assert len(applied) == 1
    assert applied[0].path == "src/App.jsx"
    assert applied[0].operation == "modified"
    assert app.read_text(encoding="utf-8") == after


def test_apply_file_changes_creates_new_file(tmp_path: Path) -> None:
    repo = tmp_path / "repo"

    applied = apply_file_changes(
        repo_path=repo,
        before_by_path={},
        changes=[
            FileChange(
                path="src/components/Card.jsx",
                content="export function Card() { return null; }\n",
            )
        ],
    )

    created = repo / "src" / "components" / "Card.jsx"

    assert len(applied) == 1
    assert applied[0].operation == "created"
    assert created.exists()
    assert "Card" in created.read_text(encoding="utf-8")


def test_apply_file_changes_skips_unchanged_file(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    app = repo / "src" / "App.jsx"
    app.parent.mkdir(parents=True)

    content = "export default function App() { return <p>Same</p>; }\n"
    app.write_text(content, encoding="utf-8")

    applied = apply_file_changes(
        repo_path=repo,
        before_by_path={"src/App.jsx": content},
        changes=[FileChange(path="src/App.jsx", content=content)],
    )

    assert applied == []


def test_apply_file_changes_rejects_parent_directory_escape(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()

    with pytest.raises(ValueError):
        apply_file_changes(
            repo_path=repo,
            before_by_path={},
            changes=[FileChange(path="../outside.txt", content="bad\n")],
        )

    assert not (tmp_path / "outside.txt").exists()


def test_apply_file_changes_rejects_absolute_path(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    outside = tmp_path / "outside.txt"

    with pytest.raises(ValueError):
        apply_file_changes(
            repo_path=repo,
            before_by_path={},
            changes=[FileChange(path=outside.as_posix(), content="bad\n")],
        )

    assert not outside.exists()


def test_write_project_patch_writes_unified_diff(tmp_path: Path) -> None:
    applied = [
        AppliedFileChange(
            path="src/App.jsx",
            operation="modified",
            before="old\n",
            after="new\n",
        )
    ]

    patch_path = tmp_path / "patch.diff"
    write_project_patch(path=patch_path, applied_changes=applied)

    patch = patch_path.read_text(encoding="utf-8")

    assert "--- a/src/App.jsx" in patch
    assert "+++ b/src/App.jsx" in patch
    assert "-old" in patch
    assert "+new" in patch


def test_write_changed_files_artifact(tmp_path: Path) -> None:
    artifact = tmp_path / "changed_files.json"

    write_changed_files_artifact(
        path=artifact,
        status="applied",
        applied_changes=[
            AppliedFileChange(
                path="src/App.jsx",
                operation="modified",
                before="old",
                after="new",
            )
        ],
        rationale="test rationale",
    )

    payload = json.loads(artifact.read_text(encoding="utf-8"))

    assert payload["status"] == "applied"
    assert payload["rationale"] == "test rationale"
    assert payload["changed_files"][0]["path"] == "src/App.jsx"
    assert payload["changed_files"][0]["operation"] == "modified"
    assert payload["changed_files"][0]["before_chars"] == 3
    assert payload["changed_files"][0]["after_chars"] == 3
