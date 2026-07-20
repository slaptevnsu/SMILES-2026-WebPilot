from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


MAX_FILE_CHARS = 12000
MAX_PROJECT_CONTEXT_CHARS = 50000

IGNORED_DIR_NAMES = {
    ".git",
    ".venv",
    "node_modules",
    "dist",
    "build",
    ".vite",
    "coverage",
}

ROOT_ALLOWED_FILES = {
    "package.json",
    "index.html",
    "vite.config.js",
    "vite.config.ts",
    "tsconfig.json",
}

SRC_ALLOWED_SUFFIXES = {
    ".js",
    ".jsx",
    ".ts",
    ".tsx",
    ".css",
    ".html",
    ".json",
}


@dataclass(frozen=True)
class ProjectFile:
    path: str
    content: str


class ProjectContextCollector:
    def collect(self, repo_path: Path) -> list[ProjectFile]:
        repo_path = repo_path.resolve()
        files: list[ProjectFile] = []

        candidate_paths = sorted(
            path
            for path in repo_path.rglob("*")
            if path.is_file() and self._should_include(path=path, repo_path=repo_path)
        )

        total_chars = 0
        for path in candidate_paths:
            relative_path = path.relative_to(repo_path).as_posix()

            try:
                content = path.read_text(encoding="utf-8")
            except UnicodeDecodeError:
                continue

            if len(content) > MAX_FILE_CHARS:
                content = (
                    content[:MAX_FILE_CHARS]
                    + "\n\n/* File truncated because it is too large. */\n"
                )

            if total_chars + len(content) > MAX_PROJECT_CONTEXT_CHARS:
                break

            files.append(ProjectFile(path=relative_path, content=content))
            total_chars += len(content)

        return files

    def format_for_prompt(self, files: list[ProjectFile]) -> str:
        sections = []

        for file in files:
            language = self._language_for_path(file.path)
            sections.extend(
                [
                    f"## File: {file.path}",
                    f"```{language}",
                    file.content,
                    "```",
                    "",
                ]
            )

        return "\n".join(sections).strip()

    def _should_include(self, *, path: Path, repo_path: Path) -> bool:
        relative_parts = path.relative_to(repo_path).parts

        if any(part in IGNORED_DIR_NAMES for part in relative_parts):
            return False

        relative_path = path.relative_to(repo_path).as_posix()

        if relative_path in ROOT_ALLOWED_FILES:
            return True

        if relative_path.startswith("src/") and path.suffix in SRC_ALLOWED_SUFFIXES:
            return True

        return False

    def _language_for_path(self, path: str) -> str:
        suffix = Path(path).suffix

        return {
            ".js": "js",
            ".jsx": "jsx",
            ".ts": "ts",
            ".tsx": "tsx",
            ".css": "css",
            ".html": "html",
            ".json": "json",
        }.get(suffix, "")


def validate_edit_path(*, repo_path: Path, relative_path: str) -> Path:
    if not relative_path:
        raise ValueError("Change path is empty.")

    candidate = Path(relative_path)

    if candidate.is_absolute():
        raise ValueError(f"Absolute paths are not allowed: {relative_path}")

    if ".." in candidate.parts:
        raise ValueError(f"Parent-directory traversal is not allowed: {relative_path}")

    if any(part in IGNORED_DIR_NAMES for part in candidate.parts):
        raise ValueError(f"Editing ignored directories is not allowed: {relative_path}")

    normalized = candidate.as_posix()

    is_allowed_root_file = normalized in ROOT_ALLOWED_FILES
    is_allowed_src_file = (
        normalized.startswith("src/")
        and candidate.suffix in SRC_ALLOWED_SUFFIXES
    )

    if not is_allowed_root_file and not is_allowed_src_file:
        raise ValueError(
            "Only root frontend config files and src/**/* frontend files can be edited. "
            f"Rejected path: {relative_path}"
        )

    repo_root = repo_path.resolve()
    resolved_path = (repo_root / candidate).resolve()

    if not resolved_path.is_relative_to(repo_root):
        raise ValueError(f"Resolved path escapes repository root: {relative_path}")

    return resolved_path
