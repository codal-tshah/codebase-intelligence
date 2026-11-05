"""`Analyzer` plugin wrapping the Python analysis (Django, FastAPI, Flask, SQLAlchemy)."""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path

from ci_core.analysis import AnalysisResult

from ci_adapters_django.adapter import ADAPTER_VERSION, analyze_django_project


class PythonAnalyzer:
    id = "python"
    name = "Python (Django, FastAPI, Flask, SQLAlchemy)"
    version = ADAPTER_VERSION
    extensions = (".py",)

    def detect(self, root: Path, files: Sequence[Path]) -> bool:
        return bool(files)

    def analyze(self, project_id: str, root: Path, files: Sequence[Path]) -> AnalysisResult:
        res = analyze_django_project(project_id, root, list(files))
        meta = {}
        if res.is_django:
            meta = {
                "installed_apps": res.installed_apps,
                "middleware": res.middleware,
                "root_urlconf": res.root_urlconf,
            }
        return AnalysisResult(
            analyzer=self.id,
            nodes=res.nodes,
            edges=res.edges,
            files=res.files,
            warnings=res.warnings,
            stats=res.stats,
            frameworks=res.frameworks,
            meta=meta,
        )


ANALYZER = PythonAnalyzer()
