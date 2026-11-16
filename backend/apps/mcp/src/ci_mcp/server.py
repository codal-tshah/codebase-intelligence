"""MCP server: expose the code graph to any MCP client (Claude Code, Claude Desktop, IDEs).

    ci mcp                      # serve the project in the current directory (indexes it if needed)
    ci mcp --project ~/src/app  # or an id/name/path
    ci-mcp                      # same entry point, standalone

Register with Claude Code:  ``claude mcp add codebase-intel -- uv run --directory <backend> ci mcp --project <repo>``

Every tool takes an optional ``project`` (id, name, or path); it defaults to the server's project.
Tools are the same grounded queries the in-app assistant uses (``ci_ai.toolspec``), so answers
from an external agent cite the same node ids and file:line locations.
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Any

from mcp.server.mcpserver import MCPServer

from ci_ai import GraphTools, run_tool
from ci_core.models import ProjectRecord
from ci_core.projects import resolve_project
from ci_core.registry import load_registry

INSTRUCTIONS = """Codebase Intelligence: a static-analysis knowledge graph of the project (API endpoints, handlers,
services, ORM models, UI components, external services, and the edges between them — including frontend→backend HTTP
calls). Start with `project_overview` or `search_nodes`, then `trace_endpoint`, `get_node`, `impact_analysis`,
`find_path` or `list_models`. Results include node ids and file:line locations; quote code with `read_source`.
Edges carry confidence; treat < 0.7 as inferred."""


class ProjectResolver:
    def __init__(self, default: str | None, *, auto_index: bool = True):
        self.default = default
        self.auto_index = auto_index
        self._tools: dict[str, GraphTools] = {}

    def resolve(self, ref: str | None) -> ProjectRecord:
        ref = (ref or self.default or os.getcwd()).strip()
        found = resolve_project(ref)
        if found:
            return found
        path = Path(ref).expanduser()
        if path.exists() and self.auto_index:
            from ci_core.settings import get_settings

            if not get_settings().path_allowed(path):
                raise ValueError(f"{path} is outside CI_PROJECT_ROOTS")
            from ci_indexer import create_project_from_path, run_index_job

            record = create_project_from_path(path.resolve())
            job = run_index_job(record.id)
            if job.status.value == "failed":
                raise ValueError(f"indexing {path} failed: {job.error}")
            return record
        raise ValueError(f"unknown project {ref!r}; call list_projects or index_project first")

    def tools(self, ref: str | None) -> GraphTools:
        project = self.resolve(ref)
        if project.id not in self._tools:
            self._tools[project.id] = GraphTools(project.id)
        return self._tools[project.id]


def build_server(default_project: str | None = None, *, auto_index: bool = True) -> MCPServer:
    resolver = ProjectResolver(default_project, auto_index=auto_index)
    server = MCPServer(name="codebase-intelligence", instructions=INSTRUCTIONS, version="0.3.0")

    def call(project: str | None, name: str, **args: Any) -> Any:
        result = run_tool(resolver.tools(project), name, args)
        return result if isinstance(result, dict) else {"results": result}

    @server.tool(description="Indexed projects (id, name, path, frameworks).")
    def list_projects() -> dict:
        return {"projects": [p.model_dump(mode="json") for p in load_registry()]}

    @server.tool(description="Index (or incrementally re-index) a local repository path. Returns the project id.")
    def index_project(path: str, full: bool = False) -> dict:
        from ci_indexer import create_project_from_path, run_index_job

        from ci_core.settings import get_settings

        if not get_settings().path_allowed(Path(path)):
            raise ValueError(f"{path} is outside CI_PROJECT_ROOTS")
        record = create_project_from_path(Path(path).expanduser())
        job = run_index_job(record.id, incremental=not full)
        resolver._tools.pop(record.id, None)
        return {"project_id": record.id, "name": record.name, "status": job.status.value, "message": job.message, "error": job.error}

    @server.tool(description="Freshness of the index vs. the working tree (fresh/dirty/stale) and changed files.")
    def index_status(project: str | None = None) -> dict:
        from ci_indexer import compute_freshness

        record = resolver.resolve(project)
        return compute_freshness(record.id, Path(record.root_path))

    @server.tool(description="Project summary: frameworks, languages, node counts and a guided reading order.")
    def project_overview(project: str | None = None) -> dict:
        return call(project, "project_overview")

    @server.tool(description="Fuzzy-search functions, classes, components, endpoints, models, modules and services.")
    def search_nodes(query: str, node_types: list[str] | None = None, limit: int = 12, project: str | None = None) -> dict:
        return call(project, "search_nodes", query=query, node_types=node_types, limit=limit)

    @server.tool(description="One node (id or name): summary, layer, role, location, HTTP calls, incoming/outgoing relations.")
    def get_node(node: str, project: str | None = None) -> dict:
        return call(project, "get_node", node=node)

    @server.tool(description="HTTP endpoints (all frameworks) with handler, guards, frontend callers and models touched.")
    def list_endpoints(query: str | None = None, project: str | None = None) -> dict:
        return call(project, "list_endpoints", query=query)

    @server.tool(description="What happens when an API is called: handler, dependencies, guards, call chain, models, external services, UI callers.")
    def trace_endpoint(route: str, method: str | None = None, project: str | None = None) -> dict:
        return call(project, "trace_endpoint", route=route, method=method)

    @server.tool(description="Callers of a function/component (id or name).")
    def get_callers(node: str, project: str | None = None) -> dict:
        return call(project, "get_callers", node=node)

    @server.tool(description="Functions called by a function/component (id or name).")
    def get_callees(node: str, project: str | None = None) -> dict:
        return call(project, "get_callees", node=node)

    @server.tool(description="Blast radius of changing a symbol or file: dependents by hop, affected endpoints, risk, notes.")
    def impact_analysis(target: str, depth: int = 3, project: str | None = None) -> dict:
        return call(project, "impact_analysis", target=target, depth=depth)

    @server.tool(description="Impact of uncommitted changes or of all files changed since a git ref (e.g. origin/main).")
    def impact_of_working_tree(depth: int = 3, base: str | None = None, project: str | None = None) -> dict:
        from ci_core.insights import impact_for_request
        from ci_indexer import compute_freshness
        from ci_parsers import git_changed_between

        record = resolver.resolve(project)
        tools = resolver.tools(project)
        root = Path(record.root_path)
        if base:
            diff = git_changed_between(root, base)
            if diff is None:
                return {"error": f"could not diff against {base!r}"}
            changed = diff
        else:
            changed = compute_freshness(record.id, root).get("changed_files", [])
        report = impact_for_request(tools.index, files=changed, depth=depth)
        report["affected"] = report["affected"][:40]
        report["source"] = "git-ref" if base else "working-tree"
        return report

    @server.tool(description="Shortest dependency path between two nodes (names or ids).")
    def find_path(source: str, target: str, project: str | None = None) -> dict:
        return call(project, "find_path", source=source, target=target)

    @server.tool(description="Data models: tables, fields, relations, and which code reads/writes each.")
    def list_models(project: str | None = None) -> dict:
        return call(project, "list_models")

    @server.tool(description="Read lines of an indexed source file (secrets redacted).")
    def read_source(path: str, start_line: int = 1, end_line: int | None = None, project: str | None = None) -> dict:
        return call(project, "read_source", path=path, start_line=start_line, end_line=end_line)

    @server.tool(description="Exact-text search across indexed files.")
    def search_code(pattern: str, limit: int = 20, project: str | None = None) -> dict:
        return call(project, "search_code", pattern=pattern, limit=limit)

    return server


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="ci-mcp", description=__doc__.splitlines()[0])
    parser.add_argument("--project", default=os.environ.get("CI_PROJECT"), help="Project id, name or path (default: cwd)")
    parser.add_argument("--no-auto-index", action="store_true", help="Fail instead of indexing unknown paths")
    parser.add_argument("--transport", choices=["stdio", "streamable-http", "sse"], default="stdio")
    args = parser.parse_args(argv)
    build_server(args.project, auto_index=not args.no_auto_index).run(transport=args.transport)


def dumps(obj: Any) -> str:  # helper for CLI --json output
    return json.dumps(obj, indent=2, default=str)


if __name__ == "__main__":
    main()
