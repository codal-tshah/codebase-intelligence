from __future__ import annotations

from ci_core.analysis import AnalysisResult, HttpCall, link_http_calls, match_endpoint
from ci_core.evidence import classify_edge, classify_http_call_record, classify_node
from ci_core.models import EdgeRecord, EdgeType, NodeRecord, NodeType
from ci_parsers import stable_node_id


def _edge(**kwargs) -> EdgeRecord:
    base: dict = {
        "id": "e1",
        "project_id": "p",
        "edge_type": EdgeType.CALLS,
        "source_id": "a",
        "target_id": "b",
        "extractor": "python.parser",
        "confidence": 0.9,
        "properties": {},
    }
    base.update(kwargs)
    return EdgeRecord(**base)


def test_import_type_only_is_low():
    ev = classify_edge(_edge(edge_type=EdgeType.IMPORTS, properties={"import_kind": "type_only"}))
    assert ev["tier"] == "low"
    assert ev["reason_code"] == "import_type_only"


def test_http_literal_variant_high():
    ev = classify_edge(
        _edge(
            edge_type=EdgeType.HTTP_CALLS,
            extractor="http.linker",
            properties={"match_variant": "literal", "method": "GET", "url": "/api/items"},
        )
    )
    assert ev["tier"] == "high"
    assert ev["reason_code"] == "http_literal_route_match"


def test_http_proxy_variant_medium():
    ev = classify_edge(
        _edge(
            edge_type=EdgeType.HTTP_CALLS,
            extractor="http.linker",
            confidence=0.65,
            properties={"match_variant": "proxy_prefix"},
        )
    )
    assert ev["tier"] == "medium"
    assert ev["reason_code"] == "http_proxy_prefix_match"


def test_unresolved_http_call_record():
    ev = classify_http_call_record({"url": "/missing", "method": "GET", "match_variant": "unresolved"})
    assert ev["tier"] == "unknown"
    assert ev["reason_code"] == "unresolved_http"


def test_inferred_model_node_low():
    node = NodeRecord(
        id="m",
        project_id="p",
        node_type=NodeType.MODEL,
        name="Stub",
        extractor="django.models",
        confidence=0.5,
        properties={"inferred": True},
    )
    assert classify_node(node)["reason_code"] == "inferred_model"


def test_aggregated_explore_edge():
    ev = classify_edge(_edge(properties={"aggregated": True}, extractor="explore.view"))
    assert ev["reason_code"] == "aggregated_relationship"


def test_link_http_calls_sets_match_variants():
    pid = "p"
    src = NodeRecord(
        id="fn",
        project_id=pid,
        node_type=NodeType.FUNCTION,
        name="fn",
        source_path="web/client.ts",
        extractor="ts",
    )
    ep = NodeRecord(
        id="ep",
        project_id=pid,
        node_type=NodeType.ENDPOINT,
        name="/items",
        source_path="api/routes.py",
        extractor="fastapi",
        properties={"route": "/items", "methods": ["GET"]},
    )
    result = AnalysisResult(
        analyzer="t",
        nodes=[src, ep],
        http_calls=[HttpCall(source_id="fn", url="/api/items", method="GET", source_path="web/client.ts", line=10)],
    )
    link_http_calls(pid, result, stable_node_id)
    call = result.nodes[0].properties["http_calls"][0]
    assert call["match_variant"] == "proxy_prefix"
    http_edge = next(e for e in result.edges if e.edge_type == EdgeType.HTTP_CALLS)
    assert http_edge.properties["match_variant"] == "proxy_prefix"


def test_http_edge_without_match_variant_legacy_safe():
    ev = classify_edge(
        _edge(
            edge_type=EdgeType.HTTP_CALLS,
            extractor="http.linker",
            confidence=0.88,
            properties={"method": "GET"},
        )
    )
    assert ev["tier"] in {"high", "medium", "low", "unknown"}
    assert ev["reason_code"]


def test_match_endpoint_returns_variant():
    eps = [
        NodeRecord(
            id="e",
            project_id="p",
            node_type=NodeType.ENDPOINT,
            name="/items",
            source_path="api/routes.py",
            extractor="t",
            properties={"route": "/items", "methods": ["POST"]},
        )
    ]
    hit = match_endpoint("/api/items", "POST", eps)
    assert hit is not None
    assert hit[2] == "proxy_prefix"
