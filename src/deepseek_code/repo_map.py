from __future__ import annotations

import ast
from dataclasses import dataclass, field
from pathlib import Path


_EXCLUDED_DIRS = {".git", ".venv", "venv", "__pycache__", ".pytest_cache", ".harness_state", ".eval_reports"}
_KEY_FILE_NAMES = {
    "README.md",
    "pyproject.toml",
    "setup.py",
    "setup.cfg",
    "requirements.txt",
    "CLAUDE.md",
    "DEEPSEEK.md",
    "ARCHITECTURE.md",
}


@dataclass
class PythonFileSummary:
    path: str
    classes: list[str] = field(default_factory=list)
    functions: list[str] = field(default_factory=list)
    imports: list[str] = field(default_factory=list)


@dataclass
class RepoMap:
    root: str
    key_files: list[str] = field(default_factory=list)
    python_files: list[PythonFileSummary] = field(default_factory=list)
    truncated: bool = False

    def to_prompt(self) -> str:
        lines = ["## 项目上下文（自动生成 Repo Map）", f"根目录: {self.root}"]
        if self.key_files:
            lines.append("关键文件:")
            lines.extend(f"- {path}" for path in self.key_files)
        if self.python_files:
            lines.append("Python 文件概览:")
            for item in self.python_files:
                parts = []
                if item.classes:
                    parts.append("classes=" + ", ".join(item.classes[:8]))
                if item.functions:
                    parts.append("functions=" + ", ".join(item.functions[:12]))
                if item.imports:
                    parts.append("imports=" + ", ".join(item.imports[:8]))
                detail = "; ".join(parts) if parts else "无顶层符号"
                lines.append(f"- {item.path}: {detail}")
        if self.truncated:
            lines.append("提示: Repo Map 已截断，仅展示前 N 个 Python 文件。")
        return "\n".join(lines)


class RepoMapBuilder:
    def __init__(self, root: str | Path, max_python_files: int = 80) -> None:
        self.root = Path(root).resolve()
        self.max_python_files = max_python_files

    def build(self) -> RepoMap:
        repo_map = RepoMap(root=str(self.root))
        if not self.root.exists():
            return repo_map

        repo_map.key_files = self._find_key_files()
        python_paths = self._find_python_files()
        repo_map.truncated = len(python_paths) > self.max_python_files
        for path in python_paths[: self.max_python_files]:
            repo_map.python_files.append(self._summarize_python_file(path))
        return repo_map

    def _find_key_files(self) -> list[str]:
        result: list[str] = []
        for name in sorted(_KEY_FILE_NAMES):
            path = self.root / name
            if path.exists() and path.is_file():
                result.append(self._relative(path))
        return result

    def _find_python_files(self) -> list[Path]:
        paths: list[Path] = []
        for path in sorted(self.root.rglob("*.py")):
            if self._is_excluded(path) or not path.is_file():
                continue
            paths.append(path)
        return paths

    def _is_excluded(self, path: Path) -> bool:
        try:
            rel = path.relative_to(self.root)
        except ValueError:
            return True
        return any(part in _EXCLUDED_DIRS for part in rel.parts)

    def _summarize_python_file(self, path: Path) -> PythonFileSummary:
        summary = PythonFileSummary(path=self._relative(path))
        try:
            tree = ast.parse(path.read_text(encoding="utf-8", errors="ignore"))
        except (SyntaxError, OSError, UnicodeDecodeError):
            return summary

        for node in tree.body:
            if isinstance(node, ast.ClassDef):
                summary.classes.append(node.name)
            elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                summary.functions.append(node.name)
            elif isinstance(node, ast.Import):
                summary.imports.extend(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom):
                module = node.module or ""
                if node.level:
                    module = "." * node.level + module
                summary.imports.append(module)
        return summary

    def _relative(self, path: Path) -> str:
        return path.relative_to(self.root).as_posix()
