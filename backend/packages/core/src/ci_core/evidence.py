"""Central evidence classification for graph nodes and edges (read-time + HTTP metadata)."""

from __future__ import annotations

from typing import Any, Literal, TypedDict

from ci_core.models import EdgeRecord, EdgeType, NodeRecord, NodeType

EvidenceTier = Literal["high", "medium", "low", "unknown"]


class Evidence(TypedDict):
    tier: EvidenceTier
    reason_code: str
    reason: str


def _evidence(tier: EvidenceTier, reason_code: str, reason: str) -> Evidence:
    return {"tier": tier, "reason_code": reason_code, "reason": reason}


def classify_node(node: NodeRecord) -> Evidence:
    props = node.properties or {}
    if props.get("inferred") or (props.get("external") and node.confidence < 0.7):
        return _evidence(
            "low",
            "inferred_model",
            "Inferred symbol or external stub; verify in source or package docs",
        )
    if node.confidence < 0.7:
        return _evidence(
            "low",
            "heuristic_resolution",
            "Node extracted with heuristic confidence; verify in source",
        )
    if node.node_type == NodeType.EXTERNAL_SERVICE:
        return _evidence("medium", "http_external_dependency", "Third-party HTTP host from static client call patterns")
    if node.extractor == "http.linker":
        return _evidence("medium", "http_external_dependency", "Created by cross-stack HTTP linker")
    return _evidence("high", "structural_containment", "Parsed structural node from source analysis")


def classify_http_call_record(rec: dict[str, Any]) -> Evidence:
    variant = rec.get("match_variant")
    if variant == "unresolved":
        return _evidence("unknown", "unresolved_http", "Backend endpoint could not be resolved for this call")
    if variant == "external":
        return _evidence("medium", "http_external_dependency", "Outbound call targets an external HTTP host")
    if variant == "proxy_prefix":
        return _evidence(
            "medium",
            "http_proxy_prefix_match",
            "Matched a backend route after stripping a dev proxy path prefix",
        )
    if variant == "literal":
        return _evidence(
            "high",
            "http_literal_route_match",
            "Frontend HTTP call matched a backend route using path and method",
        )
    if rec.get("endpoint_id"):
        return _evidence(
            "high",
            "http_literal_route_match",
            "Linked to a backend endpoint (legacy index without match_variant)",
        )
    return _evidence("unknown", "unresolved_http", "Backend endpoint could not be resolved for this call")


def classify_edge(edge: EdgeRecord, *, aggregated: bool = False) -> Evidence:
    props = dict(edge.properties or {})
    if aggregated or props.get("aggregated"):
        return _evidence(
            "medium",
            "aggregated_relationship",
            "Roll-up of multiple underlying edges in Explore; open underlying list for detail",
        )

    et = edge.edge_type
    ext = (edge.extractor or "").lower()
    conf = edge.confidence if edge.confidence is not None else 1.0

    if et == EdgeType.CONTAINS:
        return _evidence("high", "structural_containment", "Structural containment in the module or package tree")

    if et == EdgeType.HTTP_CALLS:
        variant = props.get("match_variant")
        if variant == "proxy_prefix":
            return _evidence(
                "medium",
                "http_proxy_prefix_match",
                "Matched a backend route after stripping a dev proxy path prefix",
            )
        if variant == "literal":
            return _evidence(
                "high",
                "http_literal_route_match",
                "Frontend HTTP call matched a backend route using path and method",
            )
        if ext == "http.linker" and conf >= 0.85:
            return _evidence(
                "high",
                "http_literal_route_match",
                "Cross-stack HTTP link from static client call to route (legacy index)",
            )
        if ext == "http.linker" and conf < 0.75:
            return _evidence(
                "medium",
                "http_proxy_prefix_match",
                "Cross-stack HTTP link with weaker path alignment (proxy or prefix heuristic)",
            )
        return _evidence("medium", "heuristic_resolution", "HTTP call linked with partial path evidence")

    if et == EdgeType.DEPENDS_ON and props.get("relation") == "http":
        if props.get("match_variant") == "external" or ext == "http.linker":
            return _evidence("medium", "http_external_dependency", "Depends on an external HTTP API host")
        return _evidence("medium", "heuristic_resolution", "External dependency edge")

    if et == EdgeType.IMPORTS:
        kind = props.get("import_kind")
        if kind == "type_only":
            return _evidence(
                "low",
                "import_type_only",
                "Type-checking or TYPE_CHECKING import; not used at runtime unless also imported elsewhere",
            )
        if kind == "lazy":
            return _evidence("medium", "static_import", "Import inside a function body (lazy load)")
        if props.get("has_runtime_import"):
            return _evidence("high", "static_import", "Load-time import from source AST")
        if "parser" in ext or "django" in ext or "typescript" in ext:
            return _evidence("high", "static_import", "Static import resolution from source")
        if conf < 0.75:
            return _evidence("low", "heuristic_resolution", "Import resolved with heuristic confidence")
        return _evidence("high", "static_import", "Import relationship from static analysis")

    if et in (EdgeType.ROUTES_TO, EdgeType.HANDLES):
        if conf >= 0.9:
            return _evidence("high", "framework_route", "Framework route wiring from URL configuration")
        return _evidence("medium", "framework_route", "Framework route link with weaker resolver confidence")

    if et in (EdgeType.CALLS, EdgeType.RENDERS, EdgeType.INJECTS):
        if conf < 0.7:
            return _evidence("low", "heuristic_resolution", "Call or render link from heuristic or partial resolution")
        if conf < 0.85:
            return _evidence("medium", "heuristic_resolution", "Static call graph with convention-based resolution")
        return _evidence("high", "static_call", "Direct call or render edge from static analysis")

    if et in (EdgeType.READS_MODEL, EdgeType.WRITES_MODEL, EdgeType.QUERIES, EdgeType.FK_TO):
        if conf >= 0.85:
            return _evidence("high", "framework_route", "Data model access from framework or ORM analysis")
        return _evidence("medium", "heuristic_resolution", "Model or FK relationship with partial resolution")

    if conf < 0.55:
        return _evidence("low", "insufficient_evidence", "Weak confidence or incomplete resolver metadata")
    if conf < 0.7:
        return _evidence("low", "heuristic_resolution", "Heuristic or incomplete static resolution")
    if conf < 0.85:
        return _evidence("medium", "heuristic_resolution", "Convention-based static resolution")
    if not edge.source_path and not edge.start_line:
        return _evidence("medium", "heuristic_resolution", "Relationship without source line citation")
    return _evidence("high", "static_call", "Static analysis edge with strong resolver confidence")


def edge_with_evidence(edge: EdgeRecord, *, aggregated: bool = False) -> dict[str, Any]:
    """Serializable edge payload with optional evidence block (backward-compatible keys)."""
    agg = aggregated or bool((edge.properties or {}).get("aggregated"))
    payload: dict[str, Any] = {
        "id": edge.id,
        "edge_type": edge.edge_type.value,
        "source_id": edge.source_id,
        "target_id": edge.target_id,
        "source_path": edge.source_path,
        "start_line": edge.start_line,
        "end_line": edge.end_line,
        "extractor": edge.extractor,
        "confidence": edge.confidence,
        "properties": dict(edge.properties or {}),
        "evidence": classify_edge(edge, aggregated=agg),
    }
    return payload


def decorate_graph_edge_view(edge: EdgeRecord, view: dict[str, Any], *, aggregated: bool = False) -> dict[str, Any]:
    """Attach evidence to an existing graph edge view dict."""
    out = dict(view)
    out["evidence"] = classify_edge(edge, aggregated=aggregated)
    return out
