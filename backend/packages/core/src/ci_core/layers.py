"""Architectural layer taxonomy shared by adapters, API, and UI.

Layers are a framework-neutral vocabulary (API, Data, Service, ...). Adapters
map concrete files onto them; the UI colours and filters by layer id.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass


@dataclass(frozen=True)
class LayerDef:
    id: str
    name: str
    description: str
    color: str


LAYERS: tuple[LayerDef, ...] = (
    LayerDef("api", "API", "Routes, views, serializers: how requests enter the system", "#60a5fa"),
    LayerDef("middleware", "Middleware", "Cross-cutting request/response handling and permissions", "#2dd4bf"),
    LayerDef("service", "Service", "Business logic, signals, background tasks", "#c084fc"),
    LayerDef("data", "Data", "ORM models, migrations, persistence", "#4ade80"),
    LayerDef("ui", "UI", "Templates, forms, template tags", "#f472b6"),
    LayerDef("config", "Config", "Settings, entry points, app wiring", "#fbbf24"),
    LayerDef("test", "Test", "Automated tests and fixtures", "#94a3b8"),
    LayerDef("external", "External", "Third-party services and SDKs", "#fb923c"),
)

LAYER_BY_ID: dict[str, LayerDef] = {layer.id: layer for layer in LAYERS}


def layer_catalog() -> list[dict[str, str]]:
    return [asdict(layer) for layer in LAYERS]


def layer_order(layer_id: str | None) -> int:
    for idx, layer in enumerate(LAYERS):
        if layer.id == layer_id:
            return idx
    return len(LAYERS)
