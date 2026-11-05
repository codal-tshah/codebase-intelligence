"""`ci` — Codebase Intelligence command line.

Every command that takes PROJECT accepts a project id, name, or a path inside the repo
(default: the current directory). Add `--json` for machine-readable output.
"""

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path
from typing import Any

import typer
import uvicorn

from ci_indexer import create_project_from_git, create_project_from_path, run_index_job

app = typer.Typer(add_completion=False, help="Codebase Intelligence CLI", no_args_is_help=True)

ProjectArg = typer.Option(None, "--project", "-p", help="Project id, name or path (default: current directory)")
JsonOpt = typer.Option(False, "--json", help="Print JSON instead of text")


def _emit(data: Any) -> None:
    typer.echo(json.dumps(data, indent=2, default=str))


def _require(project: str | None):
    from ci_core.projects import resolve_project

    record = resolve_project(project or ".")
    if record is None:
        typer.echo(f"Unknown project {project or '.'!r}.\nIndex it first: ci analyze <path>", err=True)
        raise typer.Exit(code=1)
    return record


def _tools(project: str | None):
    from ci_ai import GraphTools

    return GraphTools(_require(project).id)


# ------------------------------------------------------------------------ index


@app.command()
def analyze(
    target: str = typer.Argument(".", help="Local path or git URL"),
    incremental: bool = typer.Option(False, help="Skip work when files are unchanged instead of rebuilding"),
    as_json: bool = JsonOpt,
) -> None:
    """Analyze a repository and build the local index."""
    if target.startswith(("http://", "https://")) or target.endswith(".git"):
        project = create_project_from_git(target)
    else:
        project = create_project_from_path(Path(target))
    if not as_json:
        typer.echo(f"Project {project.id} ({project.name})")
    job = run_index_job(project.id, incremental=incremental)
    if as_json:
        _emit({"project": project.model_dump(mode="json"), "job": job.model_dump(mode="json")})
    if job.status.value == "failed":
        typer.echo(f"Index failed: {job.error}", err=True)
        raise typer.Exit(code=1)
    if not as_json:
        typer.echo(f"{job.message} (project {project.id})")


@app.command()
def projects(as_json: bool = JsonOpt) -> None:
    """List indexed projects."""
    from ci_core.registry import load_registry

    items = load_registry()
    if as_json:
        return _emit([p.model_dump(mode="json") for p in items])
    for p in items:
        typer.echo(f"{p.id}  {p.name:<28} {p.framework or '-':<40} {p.root_path}")


@app.command()
def analyzers(as_json: bool = JsonOpt) -> None:
    """Installed language/framework analyzers."""
    from ci_indexer import analyzer_catalog

    items = analyzer_catalog()
    if as_json:
        return _emit(items)
    for a in items:
        typer.echo(f"{a['id']:<12} v{a['version']:<4} {a['name']}  ({' '.join(a['extensions'])})")


@app.command()
def status(project: str | None = typer.Argument(None, help="Project id, name or path"), as_json: bool = JsonOpt) -> None:
    """Show index size and whether the index matches the working tree."""
    from ci_core.db import GraphStore
    from ci_indexer import compute_freshness

    record = _require(project)
    counts = GraphStore(record.id).counts()
    fresh = compute_freshness(record.id, Path(record.root_path))
    if as_json:
        return _emit({"project": record.model_dump(mode="json"), "counts": counts, "freshness": fresh})
    typer.echo(f"{record.name} @ {record.root_path}")
    typer.echo(f"frameworks={record.framework} commit={record.commit_sha}")
    typer.echo(f"nodes={counts['nodes']} edges={counts['edges']}")
    typer.echo(f"freshness={fresh['status']}: {fresh['message']}")
    for rel in fresh.get("changed_files", [])[:10]:
        typer.echo(f"  changed: {rel}")


# ------------------------------------------------------------------------ query


@app.command()
def search(query: str, project: str | None = ProjectArg, types: str | None = typer.Option(None, help="Comma-separated node types"), as_json: bool = JsonOpt) -> None:
    """Fuzzy-search nodes (functions, components, endpoints, models...)."""
    hits = _tools(project).find_symbol(query, limit=20, types={t.strip() for t in types.split(",")} if types else None)
    if as_json:
        return _emit(hits)
    for h in hits:
        loc = f"{h['path']}:{h['line']}" if h.get("path") else ""
        typer.echo(f"{h['type']:<16} {h['name']:<40} {loc}")


@app.command()
def endpoints(project: str | None = ProjectArg, query: str | None = typer.Option(None, "--filter", "-f"), as_json: bool = JsonOpt) -> None:
    """API explorer: routes with handler, frontend callers and models touched."""
    items = _tools(project).endpoints(query, limit=1000)
    if as_json:
        return _emit(items)
    for ep in items:
        handler = (ep.get("handler") or {}).get("name", "(inline)")
        models = ",".join(m["name"] for m in ep["models"]) or "-"
        callers = len(ep["callers"])
        typer.echo(f"{' '.join(ep['methods']) or 'ANY':<12} {ep['route']:<44} → {handler:<28} models={models} ui_callers={callers}")


@app.command()
def trace(route: str, method: str | None = typer.Option(None, "--method", "-X"), project: str | None = ProjectArg, as_json: bool = JsonOpt) -> None:
    """What happens when an endpoint is called (handler → services → models, plus UI callers)."""
    details = _tools(project).endpoint_details(route, method)
    if as_json:
        return _emit(details)
    if details.get("error"):
        typer.echo(details["error"], err=True)
        raise typer.Exit(code=1)
    typer.echo(f"{' '.join(details.get('methods') or [])} {details.get('route')}  ({details.get('source_path')}:{details.get('line')})")
    if details.get("handler"):
        h = details["handler"]
        typer.echo(f"  handler   {h['name']}  ({h['source_path']}:{h['line']})")
    for g in details.get("guards", []) + details.get("dependencies", []):
        typer.echo(f"  guard/dep {g['name']}")
    for step in details.get("chain", [])[1:]:
        typer.echo(f"  {step.get('relation', ''):<13} {step['type']:<14} {step['name']}  ({step.get('path')}:{step.get('line')})")
    for m in details.get("models", []):
        typer.echo(f"  data      {m['name']} ({'/'.join(m['access'])})")
    for c in details.get("callers", []):
        typer.echo(f"  called by {c['name']}  ({c['source_path']}:{c['line']})")


@app.command()
def models(project: str | None = ProjectArg, as_json: bool = JsonOpt) -> None:
    """Data models with relations and who reads/writes them."""
    items = _tools(project).models(limit=1000)
    if as_json:
        return _emit(items)
    for m in items:
        rel = ", ".join(r["to"] for r in m["relations"]) or "-"
        typer.echo(f"{m['name']:<24} table={m.get('table') or '-':<20} → {rel:<24} read_by={len(m['read_by'])} written_by={len(m['written_by'])}")


@app.command()
def tour(project: str | None = typer.Argument(None, help="Project id, name or path")) -> None:
    """Print a guided reading order for the codebase."""
    from ci_core.db import GraphStore
    from ci_core.insights import build_tour

    record = _require(project)
    index = GraphStore(record.id).load_index()
    for step in build_tour(index):
        typer.echo(f"{step['order']}. {step['title']}")
        typer.echo(f"   {step['description']}")
        for nid in step["node_ids"][:5]:
            node = index.nodes[nid]
            typer.echo(f"   - {node.name} ({node.source_path or node.node_type.value})")


@app.command()
def impact(
    files: list[str] = typer.Argument(None, help="Changed files (default: working-tree changes)"),
    project: str | None = ProjectArg,
    depth: int = typer.Option(3, help="Dependency hops to follow"),
    base: str | None = typer.Option(None, "--base", help="Git ref to diff against (e.g. origin/main): impact of everything changed since it"),
    fail_on: str | None = typer.Option(None, help="Exit 2 if risk is at least this level (low|medium|high) — for CI gates"),
    as_json: bool = JsonOpt,
) -> None:
    """Estimate the blast radius of changing files."""
    from ci_core.db import GraphStore
    from ci_core.insights import impact_for_request
    from ci_indexer import compute_freshness

    record = _require(project)
    index = GraphStore(record.id).load_index()
    root = Path(record.root_path).resolve()

    def rel(path: str) -> str:
        candidate = Path(path).expanduser()
        if candidate.exists():
            try:
                return candidate.resolve().relative_to(root).as_posix()
            except ValueError:
                pass
        return path.replace("\\", "/")

    if base and not files:
        from ci_parsers import git_changed_between

        diff = git_changed_between(root, base)
        if diff is None:
            typer.echo(f"Could not diff against {base!r} (not a git repo or unknown ref).", err=True)
            raise typer.Exit(code=1)
        files = diff
    changed = [rel(f) for f in files] if files else list(compute_freshness(record.id, root).get("changed_files", []))
    report = impact_for_request(index, files=changed, depth=depth)
    if as_json:
        _emit(report)
    elif not changed:
        typer.echo("No changed files.")
    else:
        typer.echo(f"Risk: {report['risk']['level']} (score {report['risk']['score']})")
        typer.echo(f"Changed nodes: {len(report['changed'])}  Affected: {len(report['affected'])}")
        for layer in report["layers"]:
            typer.echo(f"  layer {layer['name']}: {layer['count']}")
        for ep in report["affected_endpoints"][:10]:
            typer.echo(f"  endpoint {ep['name']}")
        for item in report["affected"][:15]:
            typer.echo(f"  [{item['hops']}] {item['node_type']} {item['name']} ({item['source_path']})")
        for note in report["notes"]:
            typer.echo(f"  note: {note}")
    levels = {"low": 0, "medium": 1, "high": 2}
    if fail_on and changed and levels.get(report["risk"]["level"], 0) >= levels.get(fail_on, 3):
        raise typer.Exit(code=2)


@app.command()
def ask(question: str, project: str | None = ProjectArg, as_json: bool = JsonOpt) -> None:
    """Ask a question about the project (agentic with an LLM, graph tools otherwise)."""
    from ci_ai.agent import chat_stream

    record = _require(project)

    async def run() -> list[dict]:
        events = []
        async for event in chat_stream(record.id, question):
            events.append(event)
            if not as_json:
                if event["event"] == "message":
                    sys.stdout.write(event["data"])
                    sys.stdout.flush()
                elif event["event"] == "tool":
                    t = json.loads(event["data"])
                    typer.echo(f"· {t['name']}({json.dumps(t['args'])}) → {t['summary']}", err=True)
                elif event["event"] == "error":
                    typer.echo(event["data"], err=True)
        return events

    events = asyncio.run(run())
    if as_json:
        return _emit(
            {
                "answer": "".join(e["data"] for e in events if e["event"] == "message"),
                "tools": [json.loads(e["data"]) for e in events if e["event"] == "tool"],
                "citations": next((json.loads(e["data"]) for e in events if e["event"] == "citations"), []),
            }
        )
    citations = next((json.loads(e["data"]) for e in events if e["event"] == "citations"), [])
    if citations:
        typer.echo("\nSources:")
        for c in citations[:10]:
            typer.echo(f"  - {c['label']}  {c.get('path') or ''}{':' + str(c['line']) if c.get('line') else ''}")


@app.command()
def export(project: str | None = ProjectArg, output: Path = typer.Option(None, "-o", help="File (default: stdout)")) -> None:
    """Export the full knowledge graph as JSON."""
    from ci_core.db import GraphStore
    from ci_core.layers import layer_catalog

    record = _require(project)
    index = GraphStore(record.id).load_index()
    payload = {
        "version": 1,
        "project": record.model_dump(mode="json"),
        "layers": layer_catalog(),
        "nodes": [n.model_dump(mode="json", exclude={"project_id"}) for n in index.nodes.values()],
        "edges": [e.model_dump(mode="json", exclude={"project_id"}) for e in index.edges],
    }
    text = json.dumps(payload, default=str)
    if output:
        output.write_text(text, encoding="utf-8")
        typer.echo(f"Wrote {len(payload['nodes'])} nodes, {len(payload['edges'])} edges to {output}")
    else:
        typer.echo(text)


# ---------------------------------------------------------------------- servers


@app.command()
def serve(
    host: str = "127.0.0.1",
    port: int = 8000,
    reload: bool = False,
    ui: Path | None = typer.Option(None, help="Serve a built dashboard (frontend/dist) at / with the API under /api"),
) -> None:
    """Run the API server (optionally with the built web dashboard)."""
    if ui is None:
        uvicorn.run("ci_api.main:app", host=host, port=port, reload=reload)
        return
    from ci_api.main import create_app

    if not (ui / "index.html").is_file():
        typer.echo(f"No index.html in {ui}. Build it with: cd frontend && npm run build", err=True)
        raise typer.Exit(code=1)
    typer.echo(f"Dashboard: http://{host}:{port}/   API: http://{host}:{port}/api")
    uvicorn.run(create_app(ui_dir=ui), host=host, port=port)


@app.command()
def mcp(
    project: str | None = typer.Option(None, "--project", "-p", help="Default project id, name or path (default: cwd)"),
    transport: str = typer.Option("stdio", help="stdio | streamable-http | sse"),
    no_auto_index: bool = typer.Option(False, help="Do not index unknown paths automatically"),
) -> None:
    """Run the MCP server so AI agents (Claude Code, IDEs) can query the code graph."""
    from ci_mcp.server import build_server

    build_server(project, auto_index=not no_auto_index).run(transport=transport)


if __name__ == "__main__":
    app()
