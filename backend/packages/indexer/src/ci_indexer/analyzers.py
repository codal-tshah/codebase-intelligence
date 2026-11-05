"""Analyzer registry: discover, select, run and merge language/framework analyzers.

Built-in analyzers are always available. Extra analyzers are discovered from the
``codebase_intelligence.analyzers`` entry-point group, so a new language can ship as
its own package::

    [project.entry-points."codebase_intelligence.analyzers"]
    golang = "my_ci_go:ANALYZER"

Set ``CI_ANALYZERS=python,typescript`` to restrict which analyzers run.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from importlib.metadata import entry_points
from pathlib import Path

from ci_core.analysis import AnalysisResult, Analyzer, link_http_calls, merge_results
from ci_core.models import EdgeType, NodeType
from ci_core.settings import get_settings
from ci_parsers import list_source_files, stable_node_id

log = logging.getLogger(__name__)
ENTRY_POINT_GROUP = "codebase_intelligence.analyzers"


def _builtin() -> list[Analyzer]:
    from ci_adapters_django import ANALYZER as python
    from ci_adapters_typescript import ANALYZER as typescript

    return [python, typescript]


def available_analyzers() -> list[Analyzer]:
    """Built-ins plus entry-point plugins (first registration of an id wins)."""
    found: dict[str, Analyzer] = {a.id: a for a in _builtin()}
    try:
        eps = entry_points(group=ENTRY_POINT_GROUP)
    except Exception:  # noqa: BLE001 - broken metadata must not break indexing
        eps = []
    for ep in eps:
        if ep.name in found:
            continue
        try:
            obj = ep.load()
        except Exception as exc:  # noqa: BLE001
            log.warning("could not load analyzer %s: %s", ep.name, exc)
            continue
        analyzer = obj() if isinstance(obj, type) else obj
        if isinstance(analyzer, Analyzer):
            found[analyzer.id] = analyzer
    wanted = set(get_settings().analyzers)
    return [a for a in found.values() if not wanted or a.id in wanted]


def analyzer_catalog() -> list[dict]:
    return [
        {"id": a.id, "name": a.name, "version": a.version, "extensions": list(a.extensions)}
        for a in available_analyzers()
    ]


def all_extensions(analyzers: list[Analyzer] | None = None) -> tuple[str, ...]:
    exts: list[str] = []
    for a in analyzers or available_analyzers():
        exts.extend(e for e in a.extensions if e not in exts)
    return tuple(exts)


def list_project_files(root: Path) -> list[Path]:
    """Every file any registered analyzer could index (used for freshness)."""
    return list_source_files(root, all_extensions())


@dataclass
class ProjectAnalysis:
    result: AnalysisResult
    version: str  # combined analyzer versions; a change forces a FULL rebuild
    analyzers: list[str]


def analyze_project(project_id: str, root: Path) -> ProjectAnalysis:
    analyzers = available_analyzers()
    files = list_source_files(root, all_extensions(analyzers))
    results: list[AnalysisResult] = []
    used: list[Analyzer] = []
    for analyzer in analyzers:
        mine = [f for f in files if f.suffix.lower() in analyzer.extensions]
        if not analyzer.detect(root, mine):
            continue
        try:
            results.append(analyzer.analyze(project_id, root, mine))
            used.append(analyzer)
        except Exception as exc:  # noqa: BLE001 - one analyzer failing must not lose the others
            log.exception("analyzer %s failed", analyzer.id)
            results.append(AnalysisResult(analyzer=analyzer.id, warnings=[f"analyzer {analyzer.id} failed: {exc}"]))

    merged = merge_results(project_id, results)
    link_stats = link_http_calls(project_id, merged, stable_node_id)
    merged.stats.update({f"http_{k}" if k != "http_calls" else k: v for k, v in link_stats.items()})
    merged.stats.update({"files": len(merged.files), "nodes": len(merged.nodes), "edges": len(merged.edges)})
    _finalize_project_node(project_id, root, merged)
    version = "+".join(f"{a.id}:{a.version}" for a in used) or "none"
    return ProjectAnalysis(result=merged, version=version, analyzers=[a.id for a in used])


def _finalize_project_node(project_id: str, root: Path, result: AnalysisResult) -> None:
    pid_node = stable_node_id(project_id, "project")
    project = next((n for n in result.nodes if n.id == pid_node), None)
    if project is None:
        return
    project.name = root.name
    languages = sorted({str(f.get("language")) for f in result.files.values() if f.get("language")})
    endpoints = sum(1 for n in result.nodes if n.node_type == NodeType.ENDPOINT)
    components = sum(1 for n in result.nodes if n.node_type == NodeType.COMPONENT)
    packages = sum(1 for n in result.nodes if n.node_type == NodeType.PACKAGE)
    links = sum(1 for e in result.edges if e.edge_type == EdgeType.HTTP_CALLS)
    fw = ", ".join(result.frameworks) if result.frameworks else " / ".join(languages) or "code"
    bits = [f"{packages} package(s)", f"{endpoints} route(s)"]
    if components:
        bits.append(f"{components} UI component(s)")
    if links:
        bits.append(f"{links} frontend→backend link(s)")
    project.properties.update(
        {
            "frameworks": result.frameworks,
            "languages": languages,
            "summary": f"{fw} project with " + ", ".join(bits) + ".",
        }
    )
