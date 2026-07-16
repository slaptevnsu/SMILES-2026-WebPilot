from __future__ import annotations

import json
import socket
import subprocess
import time
import urllib.error
import urllib.request
from contextlib import suppress
from pathlib import Path
from typing import Any

from playwright.sync_api import sync_playwright

from webpilot.schemas import BrowserRunResult, InteractionTestResult, Task
from webpilot.tester import InteractionTester


class BrowserExecutor:
    def __init__(
        self,
        host: str = "127.0.0.1",
        page_load_timeout_ms: int = 15_000,
        server_start_timeout_s: int = 30,
    ) -> None:
        self.host = host
        self.page_load_timeout_ms = page_load_timeout_ms
        self.server_start_timeout_s = server_start_timeout_s

    def run(self, repo_path: Path, run_dir: Path, task: Task) -> BrowserRunResult:
        repo_path = repo_path.resolve()
        run_dir = run_dir.resolve()
        run_dir.mkdir(parents=True, exist_ok=True)

        port = self._find_free_port()
        url = f"http://{self.host}:{port}/"

        artifacts = {
            "npm_install_log": str(run_dir / "npm_install.log"),
            "dev_server_log": str(run_dir / "dev_server.log"),
            "screenshot": str(run_dir / "screenshot.png"),
            "dom_snapshot": str(run_dir / "dom_snapshot.html"),
            "console_logs": str(run_dir / "console_logs.json"),
            "page_errors": str(run_dir / "page_errors.json"),
            "browser_result": str(run_dir / "browser_result.json"),
            "test_results": str(run_dir / "test_results.json"),
        }

        install_result = self._run_npm_install(repo_path=repo_path, log_path=run_dir / "npm_install.log")
        if install_result.returncode != 0:
            result = BrowserRunResult(
                repo_path=str(repo_path),
                url=url,
                port=port,
                status="npm_install_failed",
                artifacts=artifacts,
                console_log_count=0,
                page_error_count=1,
            )
            self._write_json(run_dir / "page_errors.json", [{"message": "npm install failed"}])
            self._write_json(run_dir / "browser_result.json", result.model_dump(mode="json"))
            return result

        dev_log_file = (run_dir / "dev_server.log").open("w", encoding="utf-8")
        server_process: subprocess.Popen[str] | None = None

        console_logs: list[dict[str, Any]] = []
        page_errors: list[dict[str, Any]] = []

        test_results = InteractionTestResult(
            status="skipped",
            checks=[],
            passed_count=0,
            failed_count=0,
            skipped_count=0,
        )

        try:
            server_process = self._start_dev_server(
                repo_path=repo_path,
                port=port,
                log_file=dev_log_file,
            )
            self._wait_until_server_is_ready(url)

            with sync_playwright() as playwright:
                browser = playwright.chromium.launch(headless=True)
                page = browser.new_page(viewport={"width": 1440, "height": 900})

                page.on("console", lambda msg: console_logs.append(self._serialize_console_message(msg)))
                page.on("pageerror", lambda exc: page_errors.append({"message": str(exc)}))

                page.goto(url, wait_until="networkidle", timeout=self.page_load_timeout_ms)
                
                test_results = InteractionTester().run(page=page, task=task)

                page.screenshot(path=str(run_dir / "screenshot.png"), full_page=True)
                (run_dir / "dom_snapshot.html").write_text(page.content(), encoding="utf-8")

                browser.close()

            if page_errors:
                status = "loaded_with_page_errors"
            elif test_results.failed_count > 0:
                status = "loaded_with_test_failures"
            else:
                status = "ok"

        except Exception as exc:
            status = "browser_execution_failed"
            page_errors.append(
                {
                    "message": str(exc),
                    "type": exc.__class__.__name__,
                }
            )

        finally:
            if server_process is not None:
                self._terminate_process(server_process)
            dev_log_file.close()

        self._write_json(run_dir / "console_logs.json", console_logs)
        self._write_json(run_dir / "page_errors.json", page_errors)
        self._write_json(run_dir / "test_results.json", test_results.model_dump(mode="json"))

        result = BrowserRunResult(
            repo_path=str(repo_path),
            url=url,
            port=port,
            status=status,
            artifacts=artifacts,
            console_log_count=len(console_logs),
            page_error_count=len(page_errors),
            test_status=test_results.status,
            passed_test_count=test_results.passed_count,
            failed_test_count=test_results.failed_count,
        )
        self._write_json(run_dir / "browser_result.json", result.model_dump(mode="json"))
        return result

    def _run_npm_install(self, repo_path: Path, log_path: Path) -> subprocess.CompletedProcess[str]:
        with log_path.open("w", encoding="utf-8") as log_file:
            return subprocess.run(
                ["npm", "install"],
                cwd=repo_path,
                stdout=log_file,
                stderr=subprocess.STDOUT,
                text=True,
                timeout=120,
                check=False,
            )

    def _start_dev_server(
        self,
        repo_path: Path,
        port: int,
        log_file: Any,
    ) -> subprocess.Popen[str]:
        return subprocess.Popen(
            ["npm", "run", "dev", "--", "--port", str(port)],
            cwd=repo_path,
            stdout=log_file,
            stderr=subprocess.STDOUT,
            text=True,
        )

    def _wait_until_server_is_ready(self, url: str) -> None:
        deadline = time.time() + self.server_start_timeout_s

        while time.time() < deadline:
            try:
                with urllib.request.urlopen(url, timeout=1) as response:
                    if 200 <= response.status < 500:
                        return
            except (urllib.error.URLError, TimeoutError):
                time.sleep(0.25)

        raise TimeoutError(f"Dev server did not become ready in time: {url}")

    def _find_free_port(self) -> int:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.bind((self.host, 0))
            return int(sock.getsockname()[1])

    def _terminate_process(self, process: subprocess.Popen[str]) -> None:
        if process.poll() is not None:
            return

        process.terminate()

        with suppress(subprocess.TimeoutExpired):
            process.wait(timeout=5)
            return

        process.kill()
        process.wait(timeout=5)

    def _serialize_console_message(self, msg: Any) -> dict[str, Any]:
        return {
            "type": msg.type,
            "text": msg.text,
            "location": msg.location,
        }

    def _write_json(self, path: Path, data: Any) -> None:
        with path.open("w", encoding="utf-8") as file:
            json.dump(data, file, indent=2, ensure_ascii=False)
            file.write("\n")