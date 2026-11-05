from pathlib import Path

from ci_core.settings import get_settings


def get_data_dir() -> Path:
    return get_settings().data_dir


def project_dir(project_id: str) -> Path:
    path = get_data_dir() / "projects" / project_id
    path.mkdir(parents=True, exist_ok=True)
    return path
