"""Generate Markdown + Mermaid docs from the graph, to commit into the analysed repository.

Mermaid renders natively on GitHub, GitLab, VS Code and Cursor, so the diagrams stay readable
without the dashboard. Every flowchart node carries its one-line summary as helper text.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from ci_core.insights import GraphIndex
from ci_core.models import EdgeType, GraphEdgeView, GraphNodeView, NodeType
from ci_core.suggestions import suggest
from ci_core.views import build_view
from ci_core.views.jobs import job_data_access, job_nodes

MAX_FLOW_NODES = 40
MAX_FLOWS = 40
_EDGE_LABEL = {
    "CALLS": "calls", "ROUTES_TO": "routes to", "READS_MODEL": "reads", "WRITES_MODEL": "writes",
    "QUERIES": "queries", "HTTP_CALLS": "HTTP", "INJECTS": "injects", "DEPENDS_ON": "uses",
    "RENDERS": "renders", "IMPORTS": "imports", "MIDDLEWARE": "middleware", "FK_TO": "FK",
}
_SHAPE = {
    "Endpoint": ('(["', '"])'), "Model": ('[("', '")]'), "Table": ('[("', '")]'),
    "ExternalService": ('{{"', '"}}'), "Component": ('("', '")'),
}


def _esc(text: str) -> str:
    return text.replace("`", "").replace('"', "#quot;").replace("<", "#lt;").replace(">", "#gt;").replace("\n", " ")


def _label(n: GraphNodeView, *, helper: bool) -> str:
    text = _esc(n.label)
    if helper and n.summary:
        summary = n.summary if len(n.summary) <= 70 else n.summary[:67] + "…"
        text += f"<br/><small>{_esc(summary)}</small>"
    return text


def mermaid_flowchart(
    nodes: list[GraphNodeView], edges: list[GraphEdgeView], *, direction: str = "LR", helper: bool = True,
    max_nodes: int = MAX_FLOW_NODES,
) -> str:
    keep = nodes[:max_nodes]
    ids = {n.id: f"n{i}" for i, n in enumerate(keep)}
    lines = [f"flowchart {direction}"]
    for n in keep:
        left, right = _SHAPE.get(n.node_type, ('["', '"]'))
        lines.append(f"  {ids[n.id]}{left}{_label(n, helper=helper)}{right}")
    seen: set[tuple[str, str, str]] = set()
    for e in sorted(edges, key=lambda e: (ids.get(e.source, ""), ids.get(e.target, ""), e.edge_type)):
        if e.source in ids and e.target in ids and e.edge_type != "CONTAINS":
            key = (e.source, e.target, e.edge_type)
            if key in seen:
                continue
            seen.add(key)
            arrow = "-.->" if (e.confidence if e.confidence is not None else 1.0) < 0.7 else "-->"
            lines.append(f"  {ids[e.source]} {arrow}|{_EDGE_LABEL.get(e.edge_type, e.edge_type.lower())}| {ids[e.target]}")
    if len(nodes) > max_nodes:
        lines.append(f"  more[\"… {len(nodes) - max_nodes} more nodes (open the dashboard)\"]")
    return "```mermaid\n" + "\n".join(lines) + "\n```"


def _slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-") or "item"


def _ordered(index: GraphIndex, payload_nodes: list[GraphNodeView], start: str) -> list[GraphNodeView]:
    """Start node first, then BFS order, so truncation keeps the head of the flow."""
    by_id = {n.id: n for n in payload_nodes}
    order, queue, seen = [], [start], {start}
    while queue:
        cur = queue.pop(0)
        if cur in by_id:
            order.append(by_id[cur])
        for e in index.outgoing.get(cur, []):
            if e.target_id in by_id and e.target_id not in seen:
                seen.add(e.target_id)
                queue.append(e.target_id)
    order += sorted((n for n in payload_nodes if n.id not in seen), key=lambda n: (n.source_path or "", n.label, n.id))
    return order


def _flow_section(index: GraphIndex, view: str, node_id: str, title: str, meta_line: str) -> str:
    payload = build_view(index, view, node_id)
    nodes = _ordered(index, payload.nodes, node_id)
    return f"### {title}\n\n{meta_line}\n\n{mermaid_flowchart(nodes, payload.edges)}\n"


def _architecture(index: GraphIndex) -> str:
    payload = build_view(index, "architecture")
    nodes = sorted(payload.nodes, key=lambda n: (n.label, n.id))
    body = mermaid_flowchart(nodes, payload.edges, helper=False, max_nodes=60)
    return "# Architecture\n\nPackages and their dependencies (edge = imports/calls rolled up).\n\n" + body + "\n"


def _api_flows(index: GraphIndex) -> str | None:
    endpoints = sorted((n for n in index.nodes.values() if n.node_type == NodeType.ENDPOINT),
                       key=lambda n: (n.name, n.source_path or ""))
    if not endpoints:
        return None
    parts = ["# API flows\n", "Each flow starts at the route and follows handler → services → models, "
             "with the UI code that calls it. Dashed arrows are inferred (confidence < 0.7).\n"]
    for ep in endpoints[:MAX_FLOWS]:
        methods = "/".join(ep.properties.get("methods") or []) or "ANY"
        where = f"`{ep.source_path}:{ep.start_line}`" if ep.source_path else ""
        parts.append(_flow_section(index, "api-flow", ep.id, f"{methods} {ep.name}", where))
    if len(endpoints) > MAX_FLOWS:
        parts.append(f"\n_{len(endpoints) - MAX_FLOWS} more endpoints: use `ci endpoints` or the dashboard._\n")
    return "\n".join(parts)


def _jobs(index: GraphIndex) -> str | None:
    jobs = job_nodes(index)
    if not jobs:
        return None
    parts = ["# Background and scheduled jobs\n", "Work that runs outside a request and what it reads or writes.\n",
             "| Job | Kind | Framework | Schedule | Writes | Source |", "|---|---|---|---|---|---|"]
    for j in jobs:
        info = j.properties["job"]
        _, writes = job_data_access(index, j.id)
        parts.append(f"| {_job_title(j)} | {info.get('kind')} | {info.get('framework')} | `{info.get('schedule') or info.get('command') or '-'}` "
                     f"| {', '.join(writes) or '-'} | `{j.source_path}:{j.start_line}` |")
    parts.append("")
    for j in jobs[:MAX_FLOWS]:
        info = j.properties["job"]
        parts.append(_flow_section(index, "jobs", j.id, _job_title(j), f"{info.get('framework')} {info.get('kind')}"))
    return "\n".join(parts)


def _job_title(j: Any) -> str:
    command = j.properties["job"].get("command")
    return f"{command} ({j.name})" if command else j.name


def _data_model(index: GraphIndex) -> str | None:
    models = [n for n in index.nodes.values() if n.node_type == NodeType.MODEL]
    if not models:
        return None
    ids = {m.id: _slug(m.name).replace("-", "_") or f"m{i}" for i, m in enumerate(models)}
    lines = ["erDiagram"]
    for m in models:
        cols = []
        for e in index.outgoing.get(m.id, []):
            f = index.nodes.get(e.target_id)
            if e.edge_type == EdgeType.CONTAINS and f is not None and f.node_type == NodeType.FIELD:
                ftype = str(f.properties.get("field_type") or "field")
                if ftype in ("relationship", "ForeignKey", "OneToOneField", "ManyToManyField"):
                    continue
                key = " PK" if f.properties.get("primary_key") else ""
                cols.append(f"    {_slug(ftype).replace('-', '_') or 'field'} {_slug(f.name).replace('-', '_')}{key}")
        lines.append(f"  {ids[m.id]} {{")
        lines.extend(cols or ["    string _"])
        lines.append("  }")
    for e in index.edges:
        if e.edge_type == EdgeType.FK_TO and e.source_id in ids and e.target_id in ids:
            lines.append(f"  {ids[e.target_id]} ||--o{{ {ids[e.source_id]} : \"{_esc(e.properties.get('field') or 'fk')}\"")
    rows = ["| Model | Table | Read by | Written by |", "|---|---|---|---|"]
    for m in models:
        inc = index.incoming.get(m.id, [])
        reads = {index.nodes[e.source_id].name for e in inc if e.edge_type == EdgeType.READS_MODEL}
        writes = {index.nodes[e.source_id].name for e in inc if e.edge_type == EdgeType.WRITES_MODEL}
        rows.append(f"| {m.name} | {m.properties.get('table') or m.properties.get('table_guess') or '-'} "
                    f"| {', '.join(sorted(reads)[:6]) or '-'} | {', '.join(sorted(writes)[:6]) or '-'} |")
    return ("# Data model\n\n```mermaid\n" + "\n".join(lines) + "\n```\n\n## Access\n\n" + "\n".join(rows) + "\n")


def _suggestions(index: GraphIndex) -> str:
    items = suggest(index)
    parts = ["# Optimization and reuse suggestions\n",
             "Generated from the dependency graph. Treat them as review leads: static analysis can miss "
             "dynamic calls.\n"]
    if not items:
        parts.append("No suggestions: no hubs, large functions, duplicates, cycles or scattered writes found.\n")
    for s in items:
        refs = ", ".join(f"`{n['source_path']}:{n['line']}`" if n["source_path"] else n["name"] for n in s["nodes"][:6])
        parts.append(f"- **[{s['severity']}] {s['title']}** ({s['kind']}). {s['detail']}  \n  {refs}")
    return "\n".join(parts) + "\n"


def render_docs(index: GraphIndex, project_name: str) -> dict[str, str]:
    """Filename → Markdown. Sections without data (no endpoints/jobs/models) are omitted."""
    files: dict[str, str] = {"architecture.md": _architecture(index), "suggestions.md": _suggestions(index)}
    for name, render in (("api-flows.md", _api_flows), ("jobs.md", _jobs), ("data-model.md", _data_model)):
        text = render(index)
        if text:
            files[name] = text
    counts: dict[str, int] = {}
    for n in index.nodes.values():
        counts[n.node_type.value] = counts.get(n.node_type.value, 0) + 1
    stats = ", ".join(f"{v} {k}" for k, v in sorted(counts.items(), key=lambda kv: -kv[1])[:8])
    toc = "\n".join(f"- [{f.removesuffix('.md').replace('-', ' ').capitalize()}]({f})" for f in files)
    files["README.md"] = (
        f"# {project_name}: codebase map\n\n"
        "Generated by Codebase Intelligence (`ci docs`). Regenerate after changes; don't edit by hand.\n\n"
        f"**Graph:** {stats}.\n\n{toc}\n"
    )
    return files


def write_docs(index: GraphIndex, project_name: str, root: Path, out_dir: str | Path = "docs/codebase-map") -> list[Path]:
    """Write the generated docs under ``root`` (refuses paths that escape the repository)."""
    root = root.resolve()
    target = (root / out_dir).resolve()
    # Strictly inside: writing into the root itself would overwrite the project's README.md.
    if root not in target.parents:
        raise ValueError(f"output directory must be a subdirectory of the repository: {out_dir}")
    target.mkdir(parents=True, exist_ok=True)
    written = []
    for name, text in render_docs(index, project_name).items():
        path = target / name
        path.write_text(text, encoding="utf-8")
        written.append(path)
    return written
