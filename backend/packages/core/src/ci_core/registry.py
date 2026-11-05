from __future__ import annotations

import json
from pathlib import Path

from ci_core.config import get_data_dir
from ci_core.models import ProjectRecord


def registry_path() -> Path:
    return get_data_dir() / "registry.json"


def load_registry() -> list[ProjectRecord]:
    path = registry_path()
    if not path.exists():
        return []
    data = json.loads(path.read_text(encoding="utf-8"))
    return [ProjectRecord.model_validate(item) for item in data]


def save_registry(projects: list[ProjectRecord]) -> None:
    path = registry_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps([p.model_dump(mode="json") for p in projects], indent=2),
        encoding="utf-8",
    )


def register_project(project: ProjectRecord) -> None:
    projects = load_registry()
    projects = [p for p in projects if p.id != project.id]
    projects.append(project)
    save_registry(projects)


def get_registered_project(project_id: str) -> ProjectRecord | None:
    for p in load_registry():
        if p.id == project_id:
            return p
    return None
