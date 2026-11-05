"""Analyzer plugin contract and framework-neutral post-processing.

An *analyzer* turns the files of one language/ecosystem into graph nodes and edges.
Several analyzers can run on the same repository (a Django backend next to a React
frontend); their results are merged, then cross-analyzer links are resolved here:

* outbound HTTP requests (``fetch('/api/items')``) are matched to Endpoint nodes
  produced by any analyzer, giving frontend -> backend edges;
* absolute URLs to third-party hosts become ExternalService nodes.

Third-party analyzers register through the ``codebase_intelligence.analyzers``
entry-point group (see ``ci_indexer.analyzers``) and only need to satisfy
:class:`Analyzer`.
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol, runtime_checkable
from urllib.parse import urlparse

from ci_core.models import EdgeRecord, EdgeType, NodeRecord, NodeType


@dataclass
class HttpCall:
    """An outbound HTTP request found in code, to be linked to an endpoint after merging."""

    source_id: str
    url: str
    method: str | None
    source_path: str
    line: int
    confidence: float = 0.8


@dataclass
class AnalysisResult:
    analyzer: str
    nodes: list[NodeRecord] = field(default_factory=list)
    edges: list[EdgeRecord] = field(default_factory=list)
    # rel path -> {"sha", "structural", "role", "lines", "language"}
    files: dict[str, dict[str, Any]] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)
    stats: dict[str, int] = field(default_factory=dict)
    frameworks: list[str] = field(default_factory=list)
    meta: dict[str, Any] = field(default_factory=dict)
    http_calls: list[HttpCall] = field(default_factory=list)


@runtime_checkable
class Analyzer(Protocol):
    """A language/framework analyzer. Implementations must be cheap to construct."""

    id: str
    name: str
    version: str
    extensions: tuple[str, ...]

    def detect(self, root: Path, files: Sequence[Path]) -> bool:
        """True if this analyzer has something to do. `files` match `extensions`."""

    def analyze(self, project_id: str, root: Path, files: Sequence[Path]) -> AnalysisResult:
        """Build nodes/edges for `files` (absolute paths under `root`)."""


# ----------------------------------------------------------------------------- routes

_PARAM_PATTERNS = (
    re.compile(r"^<[^>]+>$"),  # django <int:pk>
    re.compile(r"^\{[^}]+\}$"),  # fastapi {item_id}
    re.compile(r"^:[\w-]+\??$"),  # express :id
    re.compile(r"^\[[^\]]+\]$"),  # next.js [id]
    re.compile(r"^\(\?P<[^>]+>.*\)$"),  # django re_path (?P<pk>\d+)
    re.compile(r"^\$\{.*\}$"),  # JS template ${id}
)


def route_segments(route: str) -> tuple[str, ...]:
    """Normalise a route or request path to comparable segments; parameters become ``{}``."""
    path = route.strip()
    if "://" in path:
        path = urlparse(path).path
    path = path.split("?", 1)[0].split("#", 1)[0]
    path = path.lstrip("^").rstrip("$")
    out: list[str] = []
    for seg in path.split("/"):
        seg = seg.strip()
        if not seg:
            continue
        if any(p.match(seg) for p in _PARAM_PATTERNS) or "${" in seg:
            out.append("{}")
        else:
            out.append(seg.lower())
    return tuple(out)


def display_route(route: str) -> str:
    segs = route_segments(route)
    return "/" + "/".join(segs)


def _match_score(call: tuple[str, ...], route: tuple[str, ...], *, require_literal: bool = False) -> int | None:
    """How well a request path fits a route (higher is better), or None if it cannot match.

    equal literals 3, both parameters 2, request literal filling a route parameter 1,
    request parameter against a route literal 0 (possible, weak). At least one literal
    must match when the route has any, so `/api/x` never matches a bare `/{slug}`.
    """
    if len(call) != len(route):
        return None
    score = 0
    literal_hits = 0
    for a, b in zip(call, route):
        if a == b:
            score += 2 if a == "{}" else 3
            literal_hits += a != "{}"
        elif b == "{}":
            score += 1
        elif a == "{}":
            continue
        else:
            return None
    if literal_hits == 0 and (require_literal or any(s != "{}" for s in route)):
        return None
    return score


def _common_dirs(a: str | None, b: str | None) -> int:
    if not a or not b:
        return 0
    n = 0
    for x, y in zip(a.split("/")[:-1], b.split("/")[:-1]):
        if x != y:
            break
        n += 1
    return n


def match_endpoint(
    url: str, method: str | None, endpoints: Sequence[NodeRecord], *, near: str | None = None
) -> tuple[NodeRecord, float] | None:
    """Best Endpoint for a request path. A leading prefix segment (``/api`` behind a dev
    proxy) may be dropped from either side, at lower confidence. Ties prefer the endpoint
    sharing the most directories with `near` (the caller's file) — the same service in a monorepo."""
    call = route_segments(url)
    if not call:
        return None
    best: tuple[int, float, int, NodeRecord] | None = None
    for ep in endpoints:
        route = route_segments(str(ep.properties.get("route") or ep.name))
        methods = [m.upper() for m in ep.properties.get("methods") or []]
        if method and methods and method.upper() not in methods:
            continue
        variants = [(call, route, 0.9, False)]
        if len(call) > 1:
            variants.append((call[1:], route, 0.65, True))
        if len(route) > 1:
            variants.append((call, route[1:], 0.65, True))
        for c, r, conf, strict in variants:
            score = _match_score(c, r, require_literal=strict)
            if score is None or score == 0:
                continue
            cand = (score, conf, _common_dirs(near, ep.source_path), ep)
            if best is None or cand[:3] > best[:3]:
                best = cand
    if best is None:
        return None
    return best[3], best[1]


# --------------------------------------------------------------------------- merging


def merge_results(project_id: str, results: Sequence[AnalysisResult]) -> AnalysisResult:
    """Union analyzer outputs. Nodes with the same id (e.g. the Project node) merge properties."""
    merged = AnalysisResult(analyzer="+".join(r.analyzer for r in results) or "none")
    nodes: dict[str, NodeRecord] = {}
    edges: dict[str, EdgeRecord] = {}
    for res in results:
        for node in res.nodes:
            existing = nodes.get(node.id)
            if existing is None:
                nodes[node.id] = node
            else:
                for key, value in node.properties.items():
                    existing.properties.setdefault(key, value)
        for edge in res.edges:
            edges.setdefault(edge.id, edge)
        merged.files.update(res.files)
        merged.warnings.extend(res.warnings)
        merged.frameworks.extend(f for f in res.frameworks if f not in merged.frameworks)
        merged.meta.update(res.meta)
        merged.http_calls.extend(res.http_calls)
        for key, value in res.stats.items():
            merged.stats[key] = merged.stats.get(key, 0) + value
    merged.nodes = list(nodes.values())
    merged.edges = [e for e in edges.values() if e.source_id in nodes and e.target_id in nodes]
    merged.meta["analyzers"] = [r.analyzer for r in results]
    return merged


def link_http_calls(project_id: str, result: AnalysisResult, node_id_fn) -> dict[str, int]:
    """Resolve `result.http_calls` into HTTP_CALLS (to endpoints) and DEPENDS_ON (to hosts) edges.

    `node_id_fn(*parts)` builds stable ids (injected to keep core free of parser deps).
    Every call is also recorded on its source node under ``properties["http_calls"]``.
    """
    nodes = {n.id: n for n in result.nodes}
    endpoints = [n for n in result.nodes if n.node_type == NodeType.ENDPOINT]
    edge_ids = {e.id for e in result.edges}
    stats = {"http_calls": 0, "linked": 0, "external": 0, "unresolved": 0}

    for call in result.http_calls:
        source = nodes.get(call.source_id)
        if source is None:
            continue
        stats["http_calls"] += 1
        record: dict[str, Any] = {"method": call.method, "url": call.url, "line": call.line}
        parsed = urlparse(call.url) if "://" in call.url else None
        host = parsed.hostname if parsed else None
        local_host = host in (None, "localhost", "127.0.0.1", "0.0.0.0")

        target_id: str | None = None
        edge_type = EdgeType.HTTP_CALLS
        confidence = call.confidence
        if local_host:
            hit = match_endpoint(call.url, call.method, endpoints, near=call.source_path)
            if hit:
                target_id = hit[0].id
                confidence = min(call.confidence, hit[1])
                record["endpoint_id"] = target_id
                record["endpoint"] = hit[0].name
                stats["linked"] += 1
            else:
                stats["unresolved"] += 1
        elif host:
            target_id = node_id_fn(project_id, "external", host)
            if target_id not in nodes:
                svc = NodeRecord(
                    id=target_id,
                    project_id=project_id,
                    node_type=NodeType.EXTERNAL_SERVICE,
                    name=host,
                    extractor="http.linker",
                    confidence=0.8,
                    properties={
                        "kind": "http",
                        "layer": "external",
                        "role": "external",
                        "external": True,
                        "summary": f"External HTTP API at `{host}`.",
                    },
                )
                nodes[target_id] = svc
                result.nodes.append(svc)
            edge_type = EdgeType.DEPENDS_ON
            record["external_host"] = host
            stats["external"] += 1

        source.properties.setdefault("http_calls", []).append(record)
        if target_id is None:
            continue
        eid = node_id_fn(project_id, "edge", edge_type.value, call.source_id, target_id)
        if eid in edge_ids:
            continue
        edge_ids.add(eid)
        result.edges.append(
            EdgeRecord(
                id=eid,
                project_id=project_id,
                edge_type=edge_type,
                source_id=call.source_id,
                target_id=target_id,
                source_path=call.source_path,
                start_line=call.line,
                extractor="http.linker",
                confidence=confidence,
                properties={"method": call.method, "url": call.url, "relation": "http"},
            )
        )
    return stats
