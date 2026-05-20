from __future__ import annotations

from pathlib import Path
from typing import Optional

import yaml

from .models import EvalTask


class TaskLoadError(Exception):
    pass


class TaskLoader:
    def __init__(self, tasks_dir: Optional[str | Path] = None) -> None:
        if tasks_dir is not None:
            self._tasks_dir = Path(tasks_dir)
        else:
            self._tasks_dir = Path(__file__).parent / "tasks"

    def load_file(self, path: str | Path) -> list[EvalTask]:
        path = Path(path)
        if not path.exists():
            raise TaskLoadError(f"Task file not found: {path}")
        with open(path, encoding="utf-8") as f:
            data = yaml.safe_load(f)
        if data is None:
            return []
        if isinstance(data, dict):
            data = [data]
        if not isinstance(data, list):
            raise TaskLoadError(
                f"Expected list or dict in {path}, got {type(data).__name__}"
            )
        tasks = []
        for item in data:
            try:
                tasks.append(EvalTask(**item))
            except Exception as e:
                raise TaskLoadError(f"Invalid task in {path}: {e}") from e
        return tasks

    def load_all(self) -> list[EvalTask]:
        if not self._tasks_dir.exists():
            raise TaskLoadError(f"Tasks directory not found: {self._tasks_dir}")
        all_tasks: list[EvalTask] = []
        yaml_files = sorted(self._tasks_dir.rglob("*.yaml")) + sorted(
            self._tasks_dir.rglob("*.yml")
        )
        for yaml_file in yaml_files:
            try:
                all_tasks.extend(self.load_file(yaml_file))
            except TaskLoadError:
                continue
        all_tasks.sort(key=lambda t: t.task_id)
        return all_tasks

    def load_filtered(
        self,
        categories: Optional[list[str]] = None,
        difficulties: Optional[list[str]] = None,
        task_ids: Optional[list[str]] = None,
    ) -> list[EvalTask]:
        tasks = self.load_all()
        if task_ids:
            tasks = [t for t in tasks if t.task_id in task_ids]
        if categories:
            cat_set = {c.lower() for c in categories}
            tasks = [t for t in tasks if t.category.lower() in cat_set]
        if difficulties:
            diff_set = {d.lower() for d in difficulties}
            tasks = [t for t in tasks if t.difficulty.value.lower() in diff_set]
        return tasks
