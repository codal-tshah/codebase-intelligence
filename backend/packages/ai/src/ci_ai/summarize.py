from __future__ import annotations

import json

from ci_ai.embeddings import embed_query
from ci_core.config import project_dir
from ci_core.db import GraphStore
from ci_core.insights import top_ranked
from ci_core.layers import layer_catalog
from ci_core.models import EdgeType, NodeType
from ci_core.registry import get_registered_project
from ci_core.fingerprints import load_fingerprints
from ci_ai.llm import llm_enabled, llm_kwargs
from ci_security import sanitize_for_llm


_FRAMEWORK_LABELS = {
    "django": "Django",
    "fastapi": "FastAPI",
    "flask": "Flask",
    "sqlalchemy": "SQLAlchemy",
    "react": "React",
    "react-router": "React Router",
    "nextjs": "Next.js",
    "express": "Express",
    "nestjs": "NestJS",
    "vue": "Vue",
    "django-ninja": "Django Ninja",
}


def build_project_summary(project_id: str) -> dict:
    project = get_registered_project(project_id)
    if project is None:
        return {
            "summary": "Project not found.",
            "techStack": [],
            "patterns": [],
            "stats": {"files": 0, "lines": "0", "languages": 0},
        }
    store = GraphStore(project_id)
    index = store.load_index()
    nodes = list(index.nodes.values())
    edges = index.edges

    fingerprints = load_fingerprints(project_id) or {}
    files = fingerprints.get("files", {})
    line_count = sum(int(f.get("lines", 0)) for f in files.values())

    endpoints = [n for n in nodes if n.node_type == NodeType.ENDPOINT]
    models = [n for n in nodes if n.node_type == NodeType.MODEL and not n.properties.get("inferred")]
    packages = [n for n in nodes if n.node_type == NodeType.PACKAGE]
    routes = [e for e in edges if e.edge_type == EdgeType.ROUTES_TO]
    services = [n for n in nodes if n.node_type == NodeType.EXTERNAL_SERVICE]
    middleware = [n for n in nodes if n.node_type == NodeType.MIDDLEWARE]

    meta_path = project_dir(project_id) / "meta.json"
    meta: dict = {}
    if meta_path.exists():
        meta = json.loads(meta_path.read_text())
    installed_apps: list[str] = meta.get("installed_apps", [])

    languages = sorted({str(f.get("language")) for f in files.values() if f.get("language")}) or ["python"]
    tech_stack = [{"python": "Python", "typescript": "TypeScript/JavaScript"}.get(lang, lang.title()) for lang in languages]
    frameworks = [f.strip() for f in (project.framework or "").split(",") if f.strip()]
    tech_stack.extend(_FRAMEWORK_LABELS.get(f, f.title()) for f in frameworks)
    tech_stack.extend(s.name for s in services[:4])
    tech_stack = list(dict.fromkeys(tech_stack))

    patterns: list[str] = []
    if "django" in frameworks:
        patterns.extend(["Django MVT", "App modules", "ORM models"])
    if "fastapi" in frameworks or "flask" in frameworks:
        patterns.append("Decorator-routed HTTP API")
    if any(e.edge_type == EdgeType.INJECTS for e in edges):
        patterns.append("Dependency injection")
    if any(n.node_type == NodeType.COMPONENT for n in nodes):
        patterns.append("Component-based UI")
    if any(e.edge_type == EdgeType.HTTP_CALLS for e in edges):
        patterns.append("Frontend → backend API calls")
    if endpoints:
        patterns.append("HTTP routing layer")
    if models:
        patterns.append("Relational data model")
    if any(e.edge_type == EdgeType.SUBSCRIBES for e in edges):
        patterns.append("Signal-driven side effects")
    if middleware:
        patterns.append("Custom middleware")
    patterns = list(dict.fromkeys(patterns))[:6]

    layer_counts: dict[str, int] = {}
    for n in nodes:
        layer = n.properties.get("layer")
        if layer and n.node_type in (NodeType.MODULE, NodeType.ENDPOINT, NodeType.MODEL, NodeType.MIDDLEWARE):
            layer_counts[layer] = layer_counts.get(layer, 0) + 1
    layers = [
        {**entry, "count": layer_counts[entry["id"]]} for entry in layer_catalog() if entry["id"] in layer_counts
    ]

    hotspots = top_ranked(
        index, {NodeType.FUNCTION, NodeType.CLASS, NodeType.MODEL, NodeType.MIDDLEWARE}, 5, by="fan_in"
    )
    top_models = top_ranked(index, {NodeType.MODEL}, 5, by="fan_in")

    chunks = store.search_chunks(embed_query("project architecture overview tech stack"), limit=12)
    context_preview = "\n\n".join(
        f"# {c['source_path']}:{c['start_line']}\n{c['content'][:500]}" for c in chunks[:8]
    )

    summary = _heuristic_summary(project, endpoints, models, packages, routes, installed_apps, layers, hotspots)
    if llm_enabled() and context_preview:
        summary = _llm_summary(context_preview, summary) or summary

    return {
        "summary": summary,
        "techStack": tech_stack,
        "patterns": patterns,
        "preferExploreView": len(nodes) >= 800,
        "stats": {
            "files": len(files),
            "lines": f"{line_count / 1000:.1f}k" if line_count >= 1000 else str(line_count),
            "languages": len(languages) if files else 0,
            "components": sum(1 for n in nodes if n.node_type == NodeType.COMPONENT),
            "httpLinks": sum(1 for e in edges if e.edge_type == EdgeType.HTTP_CALLS),
            "nodes": len(nodes),
            "edges": len(edges),
            "endpoints": len(endpoints),
            "models": len(models),
        },
        "graphCoverage": {
            "routesLinked": len(routes),
            "routeLinkRate": round(len(routes) / max(len(endpoints), 1), 2),
        },
        "layers": layers,
        "hotspots": hotspots,
        "topModels": top_models,
        "integrations": [s.name for s in services],
        "warnings": meta.get("warnings", []),
    }


def _heuristic_summary(project, endpoints, models, packages, routes, installed_apps, layers, hotspots) -> str:
    fw = project.framework or "python"
    parts = [
        f"**{project.name}** is a **{fw}** codebase with "
        f"{len(packages)} package(s), {len(endpoints)} HTTP route(s), and {len(models)} data model(s). "
    ]
    if layers:
        top = sorted(layers, key=lambda layer: -layer["count"])[:3]
        parts.append("Most code sits in the " + ", ".join(f"**{layer['name']}**" for layer in top) + " layer(s). ")
    if hotspots:
        parts.append(
            "Most depended-on: " + ", ".join(f"`{h['name']}`" for h in hotspots[:3]) + " — change these with care. "
        )
    if routes:
        parts.append(
            f"{len(routes)} route→handler link(s) resolved; open the API flow view or take the guided tour to trace requests to models. "
        )
    parts.append("Ask the assistant about endpoints, data models, or what a change would affect; answers cite files and graph nodes.")
    return "".join(parts)


def _llm_summary(context: str, fallback: str) -> str | None:
    try:
        from litellm import completion

        safe_ctx, _ = sanitize_for_llm(context[:8000])
        response = completion(
            **llm_kwargs(),
            messages=[
                {
                    "role": "system",
                    "content": "Write a concise 2-3 sentence technical summary for developers onboarding to this repo. Use markdown sparingly (bold key terms). Do not invent files not in context.",
                },
                {"role": "user", "content": f"Code context:\n{safe_ctx}"},
            ],
            max_tokens=220,
        )
        text = response.choices[0].message.content
        return text.strip() if text else None
    except Exception:
        return fallback
