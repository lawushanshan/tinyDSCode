import yaml
from pathlib import Path

from deepseek_code.eval.loader import TaskLoader, TaskLoadError


def _write_yaml(tmp_path: Path, name: str, data: object) -> Path:
    p = tmp_path / name
    p.write_text(yaml.dump(data, allow_unicode=True), encoding="utf-8")
    return p


def test_load_single_task(tmp_path: Path) -> None:
    _write_yaml(tmp_path, "t.yaml", {
        "task_id": "x001",
        "prompt": "def f(): pass",
        "test_code": "assert f() is None",
        "entry_point": "f",
    })
    loader = TaskLoader(tasks_dir=tmp_path)
    tasks = loader.load_file(tmp_path / "t.yaml")
    assert len(tasks) == 1
    assert tasks[0].task_id == "x001"


def test_load_multiple_tasks(tmp_path: Path) -> None:
    _write_yaml(tmp_path, "t.yaml", [
        {"task_id": "a", "prompt": "def a(): pass", "test_code": "", "entry_point": "a"},
        {"task_id": "b", "prompt": "def b(): pass", "test_code": "", "entry_point": "b"},
    ])
    loader = TaskLoader(tasks_dir=tmp_path)
    tasks = loader.load_file(tmp_path / "t.yaml")
    assert len(tasks) == 2


def test_load_all(tmp_path: Path) -> None:
    _write_yaml(tmp_path, "a.yaml", [
        {"task_id": "a1", "prompt": "def f(): pass", "test_code": "", "entry_point": "f"},
    ])
    _write_yaml(tmp_path, "b.yaml", [
        {"task_id": "b1", "prompt": "def g(): pass", "test_code": "", "entry_point": "g"},
    ])
    loader = TaskLoader(tasks_dir=tmp_path)
    tasks = loader.load_all()
    assert len(tasks) == 2
    assert [t.task_id for t in tasks] == ["a1", "b1"]


def test_load_filtered_by_category(tmp_path: Path) -> None:
    _write_yaml(tmp_path, "t.yaml", [
        {"task_id": "s1", "prompt": "def f(): pass", "test_code": "", "entry_point": "f", "category": "string"},
        {"task_id": "a1", "prompt": "def g(): pass", "test_code": "", "entry_point": "g", "category": "algorithm"},
    ])
    loader = TaskLoader(tasks_dir=tmp_path)
    tasks = loader.load_filtered(categories=["string"])
    assert len(tasks) == 1
    assert tasks[0].task_id == "s1"


def test_load_filtered_by_difficulty(tmp_path: Path) -> None:
    _write_yaml(tmp_path, "t.yaml", [
        {"task_id": "e1", "prompt": "def f(): pass", "test_code": "", "entry_point": "f", "difficulty": "easy"},
        {"task_id": "m1", "prompt": "def g(): pass", "test_code": "", "entry_point": "g", "difficulty": "medium"},
    ])
    loader = TaskLoader(tasks_dir=tmp_path)
    tasks = loader.load_filtered(difficulties=["easy"])
    assert len(tasks) == 1


def test_load_file_not_found(tmp_path: Path) -> None:
    loader = TaskLoader(tasks_dir=tmp_path)
    try:
        loader.load_file(tmp_path / "nonexistent.yaml")
        assert False, "should raise"
    except TaskLoadError as e:
        assert "not found" in str(e)


def test_load_empty_yaml(tmp_path: Path) -> None:
    _write_yaml(tmp_path, "empty.yaml", None)
    loader = TaskLoader(tasks_dir=tmp_path)
    tasks = loader.load_file(tmp_path / "empty.yaml")
    assert tasks == []


def test_load_invalid_task_skipped(tmp_path: Path) -> None:
    _write_yaml(tmp_path, "bad.yaml", [{"task_id": "x"}])
    _write_yaml(tmp_path, "good.yaml", [
        {"task_id": "ok", "prompt": "def f(): pass", "test_code": "", "entry_point": "f"},
    ])
    loader = TaskLoader(tasks_dir=tmp_path)
    tasks = loader.load_all()
    assert len(tasks) == 1
    assert tasks[0].task_id == "ok"
