from __future__ import annotations

from ci_core.db import GraphStore
from ci_core.models import EdgeType, NodeType
from ci_indexer import analyze_project, analyzer_catalog, create_project_from_path, run_index_job


def _names(result):
    return {n.id: n.name for n in result.nodes}


def test_registry_lists_builtin_analyzers():
    ids = {a["id"] for a in analyzer_catalog()}
    assert {"python", "typescript"} <= ids


def test_fastapi_routes_prefixes_and_dependency_injection(fullstack_root):
    res = analyze_project("p", fullstack_root).result
    eps = {(tuple(n.properties.get("methods") or []), n.name) for n in res.nodes if n.node_type == NodeType.ENDPOINT}
    assert (("GET",), "/api/items") in eps
    assert (("GET",), "/api/items/{item_id}") in eps
    assert (("POST",), "/api/orders") in eps
    names = _names(res)
    injects = {(names[e.source_id], names[e.target_id]) for e in res.edges if e.edge_type == EdgeType.INJECTS}
    assert ("create_item", "get_current_user") in injects


def test_sqlalchemy_models_fields_and_foreign_keys(fullstack_root):
    res = analyze_project("p", fullstack_root).result
    names = _names(res)
    models = {n.name: n for n in res.nodes if n.node_type == NodeType.MODEL}
    assert {"Item", "Order"} <= set(models)
    assert models["Order"].properties["table"] == "orders"
    fks = {(names[e.source_id], names[e.target_id]) for e in res.edges if e.edge_type == EdgeType.FK_TO}
    assert ("Order", "Item") in fks
    reads = {(names[e.source_id], names[e.target_id]) for e in res.edges if e.edge_type == EdgeType.READS_MODEL}
    assert ("list_items", "Item") in reads and ("get_item", "Item") in reads


def test_frontend_requests_link_to_backend_endpoints(fullstack_root):
    res = analyze_project("p", fullstack_root).result
    names = _names(res)
    links = {(names[e.source_id], names[e.target_id]) for e in res.edges if e.edge_type == EdgeType.HTTP_CALLS}
    assert ("api.listItems", "/api/items") in links
    assert ("api.getItem", "/api/items/{item_id}") in links
    assert ("api.checkout", "/api/orders") in links
    hosts = {names[e.target_id] for e in res.edges if e.properties.get("relation") == "http" and e.edge_type == EdgeType.DEPENDS_ON}
    assert "api.stripe.com" in hosts
    assert res.stats["http_unresolved"] == 0


def test_index_pipeline_stores_both_languages_and_impact_crosses_stacks(data_dir, fullstack_copy):
    from ci_core.insights import compute_impact

    project = create_project_from_path(fullstack_copy)
    job = run_index_job(project.id)
    assert job.status.value == "completed", job.error
    store = GraphStore(project.id)
    stored = store.get_project()
    assert "fastapi" in stored.framework and "react" in stored.framework
    index = store.load_index()
    item_model = next(n for n in index.nodes.values() if n.node_type == NodeType.MODEL and n.name == "Item")
    report = compute_impact(index, [item_model.id], depth=6)
    affected = {a["name"] for a in report["affected"]}
    # backend model change reaches the React component that renders the list
    assert "list_items" in affected and "api.listItems" in affected and "ItemList" in affected


def test_components_view_and_end_to_end_api_flow(fullstack_root):
    from ci_core.insights import GraphIndex
    from ci_core.views import build_view, view_catalog

    res = analyze_project("p", fullstack_root).result
    index = GraphIndex.build(res.nodes, res.edges)
    catalog = {v["id"]: v for v in view_catalog(index)}
    assert catalog["components"]["available"] and catalog["components"]["count"] >= 4

    comp = build_view(index, "components")
    labels = {n.label for n in comp.nodes}
    assert {"App", "ItemList", "ItemCard", "useItems", "/api/items"} <= labels
    assert any(e.edge_type == "HTTP_CALLS" for e in comp.edges)

    endpoint = next(n for n in index.nodes.values() if n.node_type == NodeType.ENDPOINT and n.name == "/api/items" and "GET" in n.properties["methods"])
    flow = build_view(index, "api-flow", endpoint.id)
    labels = {n.label for n in flow.nodes}
    # UI component -> hook -> api client -> endpoint -> handler -> model
    assert {"ItemList", "useItems", "api.listItems", "/api/items", "list_items", "Item"} <= labels


def test_registry_reflects_detected_frameworks_after_index(data_dir, fullstack_copy):
    from ci_core.registry import get_registered_project

    project = create_project_from_path(fullstack_copy)
    run_index_job(project.id)
    registered = get_registered_project(project.id)
    assert "fastapi" in registered.framework and "react" in registered.framework
    assert registered.commit_sha == GraphStore(project.id).get_project().commit_sha


def test_dogfood_dashboard_calls_all_link_to_this_repos_api():
    """Locks in frontend -> backend linking on a real codebase: every API call in the dashboard must resolve."""
    from pathlib import Path

    repo = Path(__file__).resolve().parents[4]
    if not (repo / "frontend" / "src" / "api.ts").is_file():
        import pytest

        pytest.skip("frontend sources not present")
    stats = analyze_project("dogfood", repo).result.stats
    assert stats["http_unresolved"] == 0, stats
    assert stats["http_linked"] >= 15, stats
