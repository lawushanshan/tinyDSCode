from pathlib import Path
import json

from deepseek_code.repo_map import RepoMapBuilder


def test_repo_map_collects_key_files_and_python_symbols(tmp_path: Path) -> None:
    (tmp_path / "README.md").write_text("# demo", encoding="utf-8")
    package = tmp_path / "pkg"
    package.mkdir()
    (package / "main.py").write_text(
        "import os\nfrom pathlib import Path\n\nclass App:\n    pass\n\ndef run():\n    return 1\n",
        encoding="utf-8",
    )

    repo_map = RepoMapBuilder(tmp_path).build()

    assert repo_map.key_files == ["README.md"]
    assert len(repo_map.python_files) == 1
    summary = repo_map.python_files[0]
    assert summary.path == "pkg/main.py"
    assert summary.classes == ["App"]
    assert summary.functions == ["run"]
    assert "os" in summary.imports
    assert "pathlib" in summary.imports


def test_repo_map_excludes_virtualenv_and_cache_dirs(tmp_path: Path) -> None:
    (tmp_path / ".venv").mkdir()
    (tmp_path / ".venv" / "ignored.py").write_text("def ignored(): pass\n", encoding="utf-8")
    (tmp_path / "__pycache__").mkdir()
    (tmp_path / "__pycache__" / "ignored.py").write_text("def ignored(): pass\n", encoding="utf-8")
    (tmp_path / "kept.py").write_text("def kept(): pass\n", encoding="utf-8")

    repo_map = RepoMapBuilder(tmp_path).build()

    assert [item.path for item in repo_map.python_files] == ["kept.py"]


def test_repo_map_prunes_excluded_dirs_during_scan(tmp_path: Path) -> None:
    blocked = tmp_path / ".venv" / "deep" / "nested"
    blocked.mkdir(parents=True)
    (blocked / "ignored.py").write_text("def ignored(): pass\n", encoding="utf-8")
    (tmp_path / "kept.py").write_text("def kept(): pass\n", encoding="utf-8")

    repo_map = RepoMapBuilder(tmp_path, max_python_files=1).build()

    assert repo_map.truncated is False
    assert [item.path for item in repo_map.python_files] == ["kept.py"]


def test_repo_map_marks_truncated_without_collecting_every_python_file(tmp_path: Path) -> None:
    for index in range(3):
        (tmp_path / f"file_{index}.py").write_text(f"def f_{index}(): pass\n", encoding="utf-8")

    repo_map = RepoMapBuilder(tmp_path, max_python_files=2).build()

    assert repo_map.truncated is True
    assert [item.path for item in repo_map.python_files] == ["file_0.py", "file_1.py"]


def test_repo_map_prompt_contains_project_context(tmp_path: Path) -> None:
    (tmp_path / "mod.py").write_text("def hello(): pass\n", encoding="utf-8")

    prompt = RepoMapBuilder(tmp_path).build().to_prompt()

    assert "项目上下文" in prompt
    assert "mod.py" in prompt
    assert "functions=hello" in prompt


def test_repo_map_detects_node_project_profile(tmp_path: Path) -> None:
    (tmp_path / "package.json").write_text(
        json.dumps({
            "main": "dist/index.js",
            "types": "dist/index.d.ts",
            "scripts": {
                "dev": "vite",
                "build": "vite build",
                "test": "vitest run",
                "custom": "node scripts/custom.js",
            },
        }),
        encoding="utf-8",
    )
    (tmp_path / "pnpm-lock.yaml").write_text("", encoding="utf-8")
    src = tmp_path / "src"
    src.mkdir()
    (src / "main.ts").write_text("export {}\n", encoding="utf-8")

    repo_map = RepoMapBuilder(tmp_path).build()

    assert "package.json" in repo_map.key_files
    assert "JavaScript/TypeScript" in repo_map.profile.languages
    assert repo_map.profile.package_managers == ["pnpm"]
    assert repo_map.profile.test_commands == ["pnpm test"]
    assert "package.json#main: dist/index.js" in repo_map.profile.entry_points
    assert "package.json#types: dist/index.d.ts" in repo_map.profile.entry_points
    assert "src/main.ts" in repo_map.profile.entry_points
    assert "dev: vite" in repo_map.profile.scripts
    assert "build: vite build" in repo_map.profile.scripts
    assert "test: vitest run" in repo_map.profile.scripts
    assert all(not script.startswith("custom:") for script in repo_map.profile.scripts)
    assert "项目画像" in repo_map.to_prompt()
    assert "test_commands: pnpm test" in repo_map.to_prompt()
    assert "entry_points:" in repo_map.to_prompt()
    assert "scripts:" in repo_map.to_prompt()


def test_repo_map_skips_node_test_command_without_test_script(tmp_path: Path) -> None:
    (tmp_path / "package.json").write_text(
        json.dumps({"scripts": {"build": "vite build"}}),
        encoding="utf-8",
    )

    repo_map = RepoMapBuilder(tmp_path).build()

    assert "JavaScript/TypeScript" in repo_map.profile.languages
    assert repo_map.profile.package_managers == ["npm"]
    assert repo_map.profile.test_commands == []


def test_repo_map_detects_go_and_rust_profiles(tmp_path: Path) -> None:
    (tmp_path / "go.mod").write_text("module example.com/app\n", encoding="utf-8")
    (tmp_path / "Cargo.toml").write_text("[package]\nname = \"app\"\n", encoding="utf-8")
    go_main = tmp_path / "cmd" / "server"
    go_main.mkdir(parents=True)
    (go_main / "main.go").write_text("package main\n", encoding="utf-8")
    rust_src = tmp_path / "src"
    rust_src.mkdir()
    (rust_src / "main.rs").write_text("fn main() {}\n", encoding="utf-8")

    repo_map = RepoMapBuilder(tmp_path).build()

    assert "Go" in repo_map.profile.languages
    assert "Rust" in repo_map.profile.languages
    assert "go modules" in repo_map.profile.package_managers
    assert "cargo" in repo_map.profile.package_managers
    assert "go test ./..." in repo_map.profile.test_commands
    assert "cargo test" in repo_map.profile.test_commands
    assert "cmd/server/main.go" in repo_map.profile.entry_points
    assert "src/main.rs" in repo_map.profile.entry_points


def test_repo_map_detects_gradle_wrapper_and_dotnet_profiles(tmp_path: Path) -> None:
    (tmp_path / "build.gradle").write_text("plugins {}\n", encoding="utf-8")
    (tmp_path / "gradlew").write_text("", encoding="utf-8")
    (tmp_path / "App.csproj").write_text("<Project></Project>\n", encoding="utf-8")
    java_main = tmp_path / "src" / "main" / "java"
    java_main.mkdir(parents=True)

    repo_map = RepoMapBuilder(tmp_path).build()

    assert "Java/Kotlin" in repo_map.profile.languages
    assert ".NET" in repo_map.profile.languages
    assert "gradle" in repo_map.profile.package_managers
    assert "dotnet" in repo_map.profile.package_managers
    assert "./gradlew test" in repo_map.profile.test_commands
    assert "dotnet test" in repo_map.profile.test_commands
    assert "src/main/java" in repo_map.profile.entry_points
    assert "App.csproj" in repo_map.profile.entry_points


def test_repo_map_detects_python_entry_points(tmp_path: Path) -> None:
    (tmp_path / "pyproject.toml").write_text("[project]\nname = \"app\"\n", encoding="utf-8")
    (tmp_path / "main.py").write_text("def main(): pass\n", encoding="utf-8")
    package = tmp_path / "pkg"
    package.mkdir()
    (package / "__main__.py").write_text("print('run')\n", encoding="utf-8")

    repo_map = RepoMapBuilder(tmp_path).build()

    assert "Python" in repo_map.profile.languages
    assert "main.py" in repo_map.profile.entry_points
    assert "pkg/__main__.py" in repo_map.profile.entry_points


def test_repo_map_summarizes_lightweight_html_and_batch_directory(tmp_path: Path) -> None:
    (tmp_path / "index.html").write_text("<!DOCTYPE html>\n", encoding="utf-8")
    (tmp_path / "minicpm5-1b-api.bat").write_text("echo start\n", encoding="utf-8")

    repo_map = RepoMapBuilder(tmp_path).build()
    prompt = repo_map.to_prompt()

    assert "index.html" in repo_map.files
    assert "minicpm5-1b-api.bat" in repo_map.files
    assert "HTML/CSS" in repo_map.profile.languages
    assert "Windows Batch" in repo_map.profile.languages
    assert "index.html" in repo_map.profile.entry_points
    assert "minicpm5-1b-api.bat" in repo_map.profile.entry_points
    assert "文件概览" in prompt
