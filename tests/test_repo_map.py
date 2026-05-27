from pathlib import Path

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
