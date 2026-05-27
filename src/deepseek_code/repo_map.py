from __future__ import annotations

import ast
import json
from dataclasses import dataclass, field
from pathlib import Path


_EXCLUDED_DIRS = {".git", ".venv", "venv", "__pycache__", ".pytest_cache", ".harness_state", ".eval_reports"}
_KEY_FILE_NAMES = {
    "README.md",
    "pyproject.toml",
    "setup.py",
    "setup.cfg",
    "requirements.txt",
    "package.json",
    "pnpm-lock.yaml",
    "yarn.lock",
    "bun.lockb",
    "package-lock.json",
    "go.mod",
    "Cargo.toml",
    "pom.xml",
    "build.gradle",
    "build.gradle.kts",
    "gradlew",
    "gradlew.bat",
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
class ProjectProfile:
    languages: list[str] = field(default_factory=list)
    package_managers: list[str] = field(default_factory=list)
    test_commands: list[str] = field(default_factory=list)


@dataclass
class RepoMap:
    root: str
    key_files: list[str] = field(default_factory=list)
    profile: ProjectProfile = field(default_factory=ProjectProfile)
    python_files: list[PythonFileSummary] = field(default_factory=list)
    truncated: bool = False

    def to_prompt(self) -> str:
        lines = ["## 项目上下文（自动生成 Repo Map）", f"根目录: {self.root}"]
        if self.key_files:
            lines.append("关键文件:")
            lines.extend(f"- {path}" for path in self.key_files)
        if self.profile.languages or self.profile.package_managers or self.profile.test_commands:
            lines.append("项目画像:")
            if self.profile.languages:
                lines.append("- languages: " + ", ".join(self.profile.languages))
            if self.profile.package_managers:
                lines.append("- package_managers: " + ", ".join(self.profile.package_managers))
            if self.profile.test_commands:
                lines.append("- test_commands: " + ", ".join(self.profile.test_commands))
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
        repo_map.profile = self._build_project_profile()
        python_paths = self._find_python_files(limit=self.max_python_files + 1)
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

    def _build_project_profile(self) -> ProjectProfile:
        profile = ProjectProfile()

        if self._exists("pyproject.toml") or self._exists("requirements.txt") or self._exists("setup.py"):
            profile.languages.append("Python")
            profile.package_managers.append("pip/pyproject")
            profile.test_commands.append("pytest -q")

        if self._exists("package.json"):
            profile.languages.append("JavaScript/TypeScript")
            package_manager = self._detect_node_package_manager()
            if package_manager:
                profile.package_managers.append(package_manager)
            test_command = self._detect_node_test_command(package_manager)
            if test_command:
                profile.test_commands.append(test_command)

        if self._exists("go.mod"):
            profile.languages.append("Go")
            profile.package_managers.append("go modules")
            profile.test_commands.append("go test ./...")

        if self._exists("Cargo.toml"):
            profile.languages.append("Rust")
            profile.package_managers.append("cargo")
            profile.test_commands.append("cargo test")

        if self._exists("pom.xml"):
            profile.languages.append("Java")
            profile.package_managers.append("maven")
            profile.test_commands.append("mvn test")

        if self._exists("build.gradle") or self._exists("build.gradle.kts"):
            if "Java" not in profile.languages:
                profile.languages.append("Java/Kotlin")
            profile.package_managers.append("gradle")
            profile.test_commands.append(self._detect_gradle_test_command())

        if self._has_glob("*.sln") or self._has_glob("*.csproj") or self._has_glob("**/*.csproj"):
            profile.languages.append(".NET")
            profile.package_managers.append("dotnet")
            profile.test_commands.append("dotnet test")

        profile.languages = self._dedupe(profile.languages)
        profile.package_managers = self._dedupe(profile.package_managers)
        profile.test_commands = self._dedupe(profile.test_commands)
        return profile

    def _detect_node_package_manager(self) -> str | None:
        if self._exists("pnpm-lock.yaml"):
            return "pnpm"
        if self._exists("yarn.lock"):
            return "yarn"
        if self._exists("bun.lockb"):
            return "bun"
        if self._exists("package-lock.json"):
            return "npm"
        return "npm"

    def _detect_node_test_command(self, package_manager: str | None) -> str | None:
        try:
            data = json.loads((self.root / "package.json").read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return None
        scripts = data.get("scripts")
        if not isinstance(scripts, dict) or not scripts.get("test"):
            return None
        if package_manager == "pnpm":
            return "pnpm test"
        if package_manager == "yarn":
            return "yarn test"
        if package_manager == "bun":
            return "bun test"
        return "npm test"

    def _detect_gradle_test_command(self) -> str:
        if self._exists("gradlew"):
            return "./gradlew test"
        if self._exists("gradlew.bat"):
            return "gradlew.bat test"
        return "gradle test"

    def _exists(self, name: str) -> bool:
        return (self.root / name).exists()

    def _has_glob(self, pattern: str) -> bool:
        return any(self.root.glob(pattern))

    def _dedupe(self, items: list[str]) -> list[str]:
        result: list[str] = []
        for item in items:
            if item not in result:
                result.append(item)
        return result

    def _find_python_files(self, limit: int | None = None) -> list[Path]:
        paths: list[Path] = []

        def visit(directory: Path) -> bool:
            try:
                children = sorted(directory.iterdir(), key=lambda p: p.name)
            except OSError:
                return False

            for child in children:
                if child.is_dir():
                    if child.name in _EXCLUDED_DIRS:
                        continue
                    if visit(child):
                        return True
                elif child.is_file() and child.suffix == ".py":
                    paths.append(child)
                    if limit is not None and len(paths) >= limit:
                        return True
            return False

        visit(self.root)
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
