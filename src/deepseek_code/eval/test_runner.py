from __future__ import annotations

import subprocess
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional


@dataclass
class TestRunResult:
    exit_code: int = -1
    stdout: str = ""
    stderr: str = ""
    timeout: bool = False
    syntax_error: bool = False


class TestRunner:
    def __init__(self, timeout_seconds: int = 30) -> None:
        self.timeout_seconds = timeout_seconds

    def run(
        self,
        code: str,
        test_code: str,
        entry_point: str = "",
        timeout_seconds: Optional[int] = None,
    ) -> TestRunResult:
        timeout = timeout_seconds or self.timeout_seconds
        script = self._build_script(code, test_code)
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".py", delete=False, encoding="utf-8",
        ) as f:
            f.write(script)
            temp_path = f.name
        try:
            proc = subprocess.run(
                ["python", temp_path],
                capture_output=True,
                text=True,
                timeout=timeout,
            )
            return TestRunResult(
                exit_code=proc.returncode,
                stdout=proc.stdout,
                stderr=proc.stderr,
                syntax_error="SyntaxError" in proc.stderr,
            )
        except subprocess.TimeoutExpired:
            return TestRunResult(
                stderr=f"Execution timed out after {timeout}s",
                timeout=True,
            )
        finally:
            Path(temp_path).unlink(missing_ok=True)

    @staticmethod
    def _build_script(code: str, test_code: str) -> str:
        return f"{code}\n\n# --- Tests ---\n{test_code}\n\nprint('All tests passed.')\n"
