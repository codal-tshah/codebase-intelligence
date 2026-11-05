"""View modules: focused, renderable subgraphs of the knowledge graph.

Each diagram ("analysis module") lives in its own file and registers itself with
:func:`register_view`. The API serves :func:`view_catalog` so the UI renders whatever
modules exist; nothing in the frontend is hardcoded per view. Third-party packages
can add views through the ``codebase_intelligence.views`` entry-point group (the
entry point should import a module that calls ``register_view``).
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from ci_core.insights import GraphIndex
from ci_core.layers import layer_catalog
from ci_core.models import GraphEdgeView, GraphNodeView, GraphViewPayload, NodeType
from ci_core.views._common import MAX_NODES, edge_view, edges_between, node_view

log = logging.getLogger(__name__)

Builder = Callable[[GraphIndex, str | None], tuple[list[GraphNodeView], list[GraphEdgeView], dict[str, Any]]]


@dataclass(frozen=True)
class ViewModule:
    id: str
    label: str
    description: str
    icon: str
    build: Builder
    order: int = 100
    # Availability: the view is shown as available when any node of these types exists.
    requires: tuple[NodeType, ...] = ()
    # Node types for which this view is the best place to show a node (used for navigation).
    best_for: tuple[NodeType, ...] = ()
    focusable: bool = False  # accepts focus_node_id
    group: str = "explore"
    tags: tuple[str, ...] = field(default_factory=tuple)


_REGISTRY: dict[str, ViewModule] = {}
_PLUGINS_LOADED = False


def register_view(module: ViewModule) -> ViewModule:
    _REGISTRY[module.id] = module
    return module


def _load_plugins() -> None:
    global _PLUGINS_LOADED
    if _PLUGINS_LOADED:
        return
    _PLUGINS_LOADED = True
    from importlib.metadata import entry_points

    try:
        eps = entry_points(group="codebase_intelligence.views")
    except Exception:  # noqa: BLE001
        return
    for ep in eps:
        try:
            ep.load()
        except Exception as exc:  # noqa: BLE001
            log.warning("could not load view plugin %s: %s", ep.name, exc)


def registered_views() -> list[ViewModule]:
    _load_plugins()
    return sorted(_REGISTRY.values(), key=lambda v: (v.order, v.id))


def get_view(view_id: str) -> ViewModule | None:
    _load_plugins()
    return _REGISTRY.get(view_id)


def view_catalog(index: GraphIndex | None = None) -> list[dict[str, Any]]:
    """Every view with availability (and a node count) for the given project graph."""
    counts: dict[NodeType, int] = {}
    if index is not None:
        for node in index.nodes.values():
            counts[node.node_type] = counts.get(node.node_type, 0) + 1
    out = []
    for v in registered_views():
        count = sum(counts.get(t, 0) for t in v.requires) if v.requires else None
        out.append(
            {
                "id": v.id,
                "label": v.label,
                "description": v.description,
                "icon": v.icon,
                "group": v.group,
                "focusable": v.focusable,
                "best_for": [t.value for t in v.best_for],
                "available": index is None or not v.requires or bool(count),
                "count": count,
            }
        )
    return out


def build_view(index: GraphIndex, view: str, focus_node_id: str | None = None) -> GraphViewPayload:
    module = get_view(view) or get_view("layers")
    assert module is not None
    nodes, edges, meta = module.build(index, focus_node_id)
    present = {n.layer for n in nodes if n.layer}
    present_layers = []
    for entry in layer_catalog():
        if entry["id"] in present:
            present_layers.append({**entry, "count": sum(1 for n in nodes if n.layer == entry["id"])})
    meta = {**meta, "layers": present_layers, "node_count": len(nodes), "edge_count": len(edges)}
    return GraphViewPayload(view=module.id, nodes=nodes, edges=edges, metadata=meta)


# Built-in modules register on import (order defines the sidebar order).
from ci_core.views import (  # noqa: E402,F401
    api_flow,
    architecture,
    call_graph,
    components,
    er,
    integrations,
    layers,
)

VIEW_IDS = tuple(v.id for v in registered_views())

__all__ = [
    "MAX_NODES",
    "VIEW_IDS",
    "ViewModule",
    "build_view",
    "edge_view",
    "edges_between",
    "get_view",
    "node_view",
    "register_view",
    "registered_views",
    "view_catalog",
]
