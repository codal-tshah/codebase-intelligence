"""Regression tests from validating against a large real FastAPI service (see the fixture README)."""

from __future__ import annotations

from collections import deque
from pathlib import Path

import pytest

from ci_core.insights import GraphIndex
from ci_core.models import EdgeType, NodeType

FIXTURE = Path(__file__).resolve().parents[4] / "benchmarks" / "fixtures" / "layered_fastapi"


@pytest.fixture(scope="module")
def analysis(tmp_path_factory):
    import os

    old = os.environ.get("CI_DATA_DIR")
    os.environ["CI_DATA_DIR"] = str(tmp_path_factory.mktemp("data"))
    from ci_indexer.analyzers import analyze_project

    try:
        yield analyze_project("layered", FIXTURE)
    finally:
        if old is None:
            os.environ.pop("CI_DATA_DIR", None)
        else:
            os.environ["CI_DATA_DIR"] = old


@pytest.fixture(scope="module")
def index(analysis) -> GraphIndex:
    return GraphIndex.build(analysis.result.nodes, analysis.result.edges)


def _by_name(index, node_type, name):
    return next(n for n in index.nodes.values() if n.node_type == node_type and n.name == name)


def test_every_file_parses_including_pep758_except(analysis, index):
    assert analysis.result.warnings == []
    assert any(n.qualified_name == "app.core.errors.to_int" for n in index.nodes.values())


def test_empty_path_routes_are_the_router_prefix(index):
    routes = sorted(
        (n.properties["methods"][0], n.name) for n in index.nodes.values() if n.node_type == NodeType.ENDPOINT
    )
    assert routes == [("GET", "/v1/widgets"), ("GET", "/v1/widgets/{widget_id}"), ("POST", "/v1/widgets")]


def test_generated_htmlcov_is_not_indexed(index):
    assert not any((n.source_path or "").startswith("htmlcov") for n in index.nodes.values())
    assert not any(n.node_type == NodeType.PACKAGE and n.name == "layered_fastapi" for n in index.nodes.values())


def test_nested_packages_give_explore_a_hierarchy(index):
    pkgs = {n.qualified_name: n for n in index.nodes.values() if n.node_type == NodeType.PACKAGE}
    assert {"app", "app.cycles", "app.routers", "app.routers.v1", "app.services"} <= set(pkgs)
    assert pkgs["app.routers.v1"].properties.get("subpackage") is True
    assert index.contains_parent[pkgs["app.routers.v1"].id] == pkgs["app.routers"].id


def test_fastapi_folder_roles_and_layers(index):
    def mod(rel):
        return next(n for n in index.nodes.values() if n.node_type == NodeType.MODULE and n.source_path == rel)

    assert mod("app/routers/v1/widgets.py").properties["layer"] == "api"
    assert mod("app/schemas/widgets.py").properties["role"] == "serializers"
    assert mod("app/repositories/widgets.py").properties["role"] == "repositories"
    assert mod("app/repositories/widgets.py").properties["layer"] == "data"
    assert mod("app/dependencies/services.py").properties["role"] == "dependencies"
    assert mod("app/db/session.py").properties["layer"] == "data"


def test_typed_dependencies_resolve_handler_to_service_to_repository_to_model(index):
    handler = next(n for n in index.nodes.values() if n.qualified_name == "app.routers.v1.widgets.list_widgets")
    widget = _by_name(index, NodeType.MODEL, "Widget")
    names = {}
    seen = {handler.id}
    queue = deque([(handler.id, 0)])
    while queue:
        cur, d = queue.popleft()
        for e in index.outgoing.get(cur, []):
            if e.edge_type in (EdgeType.CALLS, EdgeType.READS_MODEL, EdgeType.WRITES_MODEL) and e.target_id not in seen:
                seen.add(e.target_id)
                names[index.nodes[e.target_id].qualified_name] = d + 1
                queue.append((e.target_id, d + 1))
    assert names.get("app.services.widgets.WidgetService.list_widgets") == 1  # `service: WidgetServiceDep`
    assert names.get("app.repositories.widgets.WidgetRepository.list_active") == 2  # `self.repo` typed in __init__
    assert widget.qualified_name in names


def test_api_flow_columns_for_one_endpoint(index):
    from ci_core.views.api_flow import build

    ep = next(
        n
        for n in index.nodes.values()
        if n.node_type == NodeType.ENDPOINT and n.name == "/v1/widgets" and n.properties["methods"] == ["POST"]
    )
    nodes, edges, meta = build(index, ep.id)
    cols = {n.properties["column"]: [] for n in nodes}
    for n in nodes:
        cols[n.properties["column"]].append(n.label)
    assert meta["layout"] == "columns"
    assert cols["endpoint"] == ["/v1/widgets"] and cols["handler"] == ["create_widget"]
    assert "WidgetService.create" in cols["service"]
    assert "WidgetRepository.add" in cols["data_access"]
    assert "Widget" in cols["model"]
    assert not any(
        "WidgetOut" in label or "WidgetIn" in label for v in cols.values() for label in v
    )  # schemas aren't steps
    assert all(e.source in {n.id for n in nodes} and e.target in {n.id for n in nodes} for e in edges)


@pytest.mark.parametrize(
    ("path", "role"),
    [
        ("app/routers/v1/items.py", "views"),
        ("app/api/v1/items.py", "views"),
        ("shop/api/serializers.py", "serializers"),  # Django REST layout keeps its role
        ("app/schemas/items.py", "serializers"),
        ("app/repositories/items.py", "repositories"),
        ("app/dependencies/auth.py", "dependencies"),
        ("app/db/session.py", "database"),
        ("app/workers/sync.py", "tasks"),
        ("alembic/versions/2024_01_01_add_items.py", "migration"),
        ("alembic/env.py", "settings"),
        ("shop/migrations/0001_initial.py", "migration"),
        ("app/services/items.py", "services"),
    ],
)
def test_module_roles_for_common_python_layouts(path, role):
    from ci_adapters_django.roles import classify_module

    assert classify_module(path) == role


def test_suggest_reports_only_runtime_import_cycles(index):
    from ci_core.suggestions import suggest

    cycles = [s for s in suggest(index) if s["kind"] == "cycle"]
    assert len(cycles) == 1
    names = {n["name"] for n in cycles[0]["nodes"]}
    assert names == {"app/cycles/rt_a", "app/cycles/rt_b"}


def test_architecture_opens_a_dominant_app_into_its_layers(index):
    from ci_core.views.architecture import build

    nodes, edges, _ = build(index, None)
    labels = {n.label for n in nodes}
    assert {"app", "routers", "services", "repositories", "models"} <= labels
    assert "v1" not in labels  # only the first level below the app
    assert edges
