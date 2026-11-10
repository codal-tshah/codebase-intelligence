from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path
from typing import Any

from ci_core.db import GraphStore
from ci_core.insights import (
    GraphIndex,
    build_tour,
    describe_endpoint,
    find_path,
    impact_for_request,
    list_endpoints,
    search_nodes,
)
from ci_core.models import EdgeType, NodeRecord, NodeType
from ci_core.serializers import tool_node_brief
from ci_core.source import resolve_source_path
from ci_security import sanitize_for_llm


def _brief(n: NodeRecord) -> dict[str, Any]:
    return tool_node_brief(n)


class GraphTools:
    """Deterministic graph queries used as grounding for the assistant (and callable directly)."""

    def __init__(self, project_id: str):
        self.store = GraphStore(project_id)
        project = self.store.get_project()
        if project is None:
            raise ValueError("project not found")
        self.root = Path(project.root_path)
        self._index: GraphIndex | None = None
        self._allowed: set[str] | None = None

    @property
    def index(self) -> GraphIndex:
        if self._index is None:
            self._index = self.store.load_index()
        return self._index

    @property
    def allowed_paths(self) -> set[str]:
        if self._allowed is None:
            self._allowed = self.store.indexed_paths()
        return self._allowed

    # ---------------------------------------------------------------- lookup

    def resolve(self, query: str) -> NodeRecord | None:
        """A node id, an exact file path, or the best fuzzy match for a name."""
        q = (query or "").strip()
        if not q:
            return None
        if q in self.index.nodes:
            return self.index.nodes[q]
        for n in self.index.nodes.values():
            if n.source_path == q and n.node_type in (NodeType.MODULE, NodeType.MIGRATION):
                return n
        hits = search_nodes(self.index.nodes.values(), q, limit=1)
        return hits[0][0] if hits else None

    def find_symbol(self, name: str, limit: int = 12, types: set[str] | None = None) -> list[dict]:
        hits = search_nodes(self.index.nodes.values(), name, limit=limit, types=types)
        return [{**_brief(n), "score": score} for n, score in hits]

    def get_node(self, node_id: str) -> dict | None:
        node = self.index.nodes.get(node_id) or self.resolve(node_id)
        if node is not None:
            node_id = node.id
        if not node:
            return None
        edges = [
            *self.index.outgoing.get(node_id, []),
            *self.index.incoming.get(node_id, []),
        ]
        return {
            **_brief(node),
            "lines": [node.start_line, node.end_line],
            "complexity": node.properties.get("complexity"),
            "tags": node.properties.get("tags", []),
            "role": node.properties.get("role"),
            "http_calls": node.properties.get("http_calls", [])[:10],
            "methods": node.properties.get("methods"),
            "route": node.properties.get("route"),
            "edges": [
                {
                    "type": e.edge_type.value,
                    "source": e.source_id,
                    "target": e.target_id,
                    "other": self.index.nodes[e.target_id if e.source_id == node_id else e.source_id].name,
                }
                for e in edges
                if e.edge_type != EdgeType.CONTAINS
            ][:40],
        }

    def _neighbours(self, node_id: str, edge_type: EdgeType, *, incoming: bool) -> list[dict]:
        edges = self.index.incoming.get(node_id, []) if incoming else self.index.outgoing.get(node_id, [])
        out = []
        for e in edges:
            if e.edge_type == edge_type:
                other = self.index.nodes[e.source_id if incoming else e.target_id]
                out.append({"id": other.id, "name": other.name, "path": other.source_path})
        return out

    def get_callers(self, node_id: str) -> list[dict]:
        return self._neighbours(node_id, EdgeType.CALLS, incoming=True)

    def get_callees(self, node_id: str) -> list[dict]:
        return self._neighbours(node_id, EdgeType.CALLS, incoming=False)

    # ------------------------------------------------------------ flows

    def trace_endpoint(self, route: str) -> dict:
        needle = route.strip().strip("/").lower()
        endpoints = [n for n in self.index.nodes.values() if n.node_type == NodeType.ENDPOINT]
        matches = [n for n in endpoints if n.id == route] or [
            n for n in endpoints if needle and needle in n.name.lower().strip("/")
        ]
        if not matches:
            return {"error": "endpoint not found", "route": route}
        matches.sort(key=lambda n: (n.name.strip("/").lower() != needle, len(n.name)))
        ep = matches[0]
        chain = [{"type": "endpoint", "id": ep.id, "name": ep.name, "path": ep.source_path, "line": ep.start_line}]
        seen = {ep.id}
        frontier = [ep.id]
        follow = {
            EdgeType.ROUTES_TO, EdgeType.CALLS, EdgeType.READS_MODEL, EdgeType.WRITES_MODEL,
            EdgeType.DEPENDS_ON, EdgeType.INJECTS,
        }
        for _ in range(3):
            nxt: list[str] = []
            for cur in frontier:
                for e in self.index.outgoing.get(cur, []):
                    if e.edge_type in follow and e.target_id not in seen:
                        seen.add(e.target_id)
                        node = self.index.nodes[e.target_id]
                        chain.append(
                            {
                                "type": node.node_type.value.lower(),
                                "relation": e.edge_type.value,
                                "id": node.id,
                                "name": node.name,
                                "path": node.source_path,
                                "line": node.start_line,
                            }
                        )
                        nxt.append(node.id)
            frontier = nxt
        return {
            "route": ep.name,
            "methods": ep.properties.get("methods"),
            "chain": chain[:30],
            "others": [m.name for m in matches[1:6]],
        }

    def endpoints(self, query: str | None = None, limit: int = 60) -> list[dict]:
        return list_endpoints(self.index, query=query)[:limit]

    def endpoint_details(self, route: str, method: str | None = None) -> dict:
        """Best-matching endpoint with handler, guards, callers (frontend), models and a call chain."""
        from ci_core.analysis import match_endpoint

        eps = [n for n in self.index.nodes.values() if n.node_type == NodeType.ENDPOINT]
        node = self.index.nodes.get(route)
        if node is None or node.node_type != NodeType.ENDPOINT:
            hit = match_endpoint(route, method, eps)
            node = hit[0] if hit else None
        if node is None:
            trace = self.trace_endpoint(route)
            return trace
        details = describe_endpoint(self.index, node)
        details["chain"] = self.trace_endpoint(node.id)["chain"] if node else []
        return details

    def models(self, limit: int = 80) -> list[dict]:
        """ORM models with fields, relations, and the code that reads/writes them."""
        out = []
        for m in sorted(
            (n for n in self.index.nodes.values() if n.node_type == NodeType.MODEL),
            key=lambda n: (-self.index.fan_in(n.id), n.name),
        )[:limit]:
            fields, relations, readers, writers = [], [], set(), set()
            for e in self.index.outgoing.get(m.id, []):
                target = self.index.nodes[e.target_id]
                if e.edge_type == EdgeType.CONTAINS and target.node_type == NodeType.FIELD:
                    fields.append(f"{target.name}: {target.properties.get('field_type', '')}")
                elif e.edge_type == EdgeType.FK_TO:
                    relations.append({"to": target.name, "to_id": target.id, "field": e.properties.get("field"), "relation": e.properties.get("relation")})
            for e in self.index.incoming.get(m.id, []):
                src = self.index.nodes[e.source_id].name
                if e.edge_type == EdgeType.READS_MODEL:
                    readers.add(src)
                elif e.edge_type == EdgeType.WRITES_MODEL:
                    writers.add(src)
            out.append(
                {
                    **_brief(m),
                    "table": m.properties.get("table") or m.properties.get("table_guess"),
                    "fields": fields[:40],
                    "relations": relations,
                    "read_by": sorted(readers)[:20],
                    "written_by": sorted(writers)[:20],
                }
            )
        return out

    def overview(self) -> dict:
        project = self.store.get_project()
        project_node = next((n for n in self.index.nodes.values() if n.node_type == NodeType.PROJECT), None)
        counts: dict[str, int] = {}
        for n in self.index.nodes.values():
            counts[n.node_type.value] = counts.get(n.node_type.value, 0) + 1
        return {
            "name": project.name if project else None,
            "frameworks": project.framework if project else None,
            "summary": project_node.properties.get("summary") if project_node else None,
            "languages": project_node.properties.get("languages") if project_node else None,
            "counts": counts,
            "tour": [{"order": s["order"], "title": s["title"], "description": s["description"]} for s in self.tour()],
        }

    def list_models_for_view(self, view_name: str) -> list[dict]:
        hits = search_nodes(
            self.index.nodes.values(),
            view_name,
            types={NodeType.FUNCTION.value, NodeType.CLASS.value},
            limit=5,
        )
        models = []
        for view, _ in hits:
            for e in self.index.outgoing.get(view.id, []):
                if e.edge_type in (EdgeType.READS_MODEL, EdgeType.WRITES_MODEL):
                    model = self.index.nodes[e.target_id]
                    models.append(
                        {
                            "view": view.name,
                            "model": model.name,
                            "model_id": model.id,
                            "access": "write" if e.edge_type == EdgeType.WRITES_MODEL else "read",
                            "path": model.source_path,
                        }
                    )
        return models

    def find_path(self, source_query: str, target_query: str) -> dict:
        a, b = self.resolve(source_query), self.resolve(target_query)
        if a is None or b is None:
            return {"found": False, "reason": "could not resolve one of the endpoints"}
        result = find_path(self.index, a.id, b.id)
        result["steps"] = [
            {"id": nid, "name": self.index.nodes[nid].name, "path": self.index.nodes[nid].source_path}
            for nid in result.get("node_ids", [])
        ]
        return result

    def impact_of(self, query: str, depth: int = 3) -> dict:
        """What breaks if `query` (a symbol name or file path) changes?"""
        q = query.strip().replace("\\", "/")
        files: list[str] = []
        node_ids: list[str] = []
        if any(n.source_path == q for n in self.index.nodes.values()):
            files = [q]
        else:
            hit = self.resolve(q)
            if hit:
                node_ids = [hit.id]
            else:
                return {"error": f"no node matches {q!r}", "affected": [], "changed": []}
        report = impact_for_request(self.index, files=files, node_ids=node_ids, depth=depth)
        report["affected"] = report["affected"][:25]
        return report

    def tour(self) -> list[dict]:
        return build_tour(self.index)

    # ----------------------------------------------------------- source

    def read_source_snippet(self, path: str, start: int = 1, end: int | None = None) -> dict:
        safe_path = resolve_source_path(self.root, path, self.allowed_paths)
        if safe_path is None:
            return {"error": "path is not an indexed source file"}
        lines = safe_path.read_text(encoding="utf-8", errors="replace").splitlines()
        end = min(end or start + 40, len(lines), start + 200)
        snippet, _ = sanitize_for_llm("\n".join(lines[start - 1 : end]))
        return {"path": path, "start": start, "end": end, "content": snippet}

    def search_code(self, pattern: str, limit: int = 20) -> list[dict]:
        try:
            proc = subprocess.run(
                ["rg", "--json", "-n", "--fixed-strings", pattern, str(self.root)],
                capture_output=True,
                text=True,
                check=False,
                timeout=15,
            )
        except (FileNotFoundError, subprocess.TimeoutExpired):
            return self._python_search(pattern, limit)
        hits = []
        for line in proc.stdout.splitlines():
            if not line.strip():
                continue
            try:
                obj = json.loads(line)
            except json.JSONDecodeError:
                continue
            if obj.get("type") != "match":
                continue
            data = obj.get("data", {})
            path = data.get("path", {}).get("text", "")
            if not path:
                continue
            rel = Path(path).resolve().relative_to(self.root.resolve()).as_posix()
            if rel not in self.allowed_paths:
                continue
            text, _ = sanitize_for_llm(data.get("lines", {}).get("text", "").strip())
            hits.append({"path": rel, "line": data.get("line_number"), "text": text})
            if len(hits) >= limit:
                break
        return hits

    def _python_search(self, pattern: str, limit: int) -> list[dict]:
        rx = re.compile(re.escape(pattern), re.IGNORECASE)
        hits = []
        for rel in sorted(self.allowed_paths):
            path = self.root / rel
            if not path.is_file():
                continue
            for i, line in enumerate(path.read_text(encoding="utf-8", errors="replace").splitlines(), start=1):
                if rx.search(line):
                    text, _ = sanitize_for_llm(line.strip())
                    hits.append({"path": rel, "line": i, "text": text})
                    if len(hits) >= limit:
                        return hits
        return hits
