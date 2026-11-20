#!/usr/bin/env python3
"""Time the graph analytics on an already-indexed project (read-only).

uv run python scripts/benchmark_graph.py --largest
uv run python scripts/benchmark_graph.py --project my-repo --repeat 5 --json out.json
"""

from __future__ import annotations

import argparse
import json
import random
import statistics
import sys
import time
from pathlib import Path

from ci_core import db as dbmod
from ci_core.db import GraphStore, db_path_for_project
from ci_core.insights import DEPENDENCY_EDGES, GraphIndex, compute_impact, find_path, neighborhood_subgraph
from ci_core.models import NodeType
from ci_core.projects import resolve_project
from ci_core.registry import load_registry


def _ms(fn, repeat: int) -> dict[str, float]:
    runs = []
    for _ in range(repeat):
        t0 = time.perf_counter()
        fn()
        runs.append((time.perf_counter() - t0) * 1000)
    return {"median_ms": round(statistics.median(runs), 2), "max_ms": round(max(runs), 2), "runs": repeat}


def _pick_project(ref: str | None, largest: bool):
    if ref:
        project = resolve_project(ref)
        if project is None:
            sys.exit(f"unknown project: {ref}")
        return project
    projects = [p for p in load_registry() if db_path_for_project(p.id).exists()]
    if not projects:
        sys.exit("no indexed projects found")
    if largest:
        return max(projects, key=lambda p: db_path_for_project(p.id).stat().st_size)
    sys.exit("pass --project <name|id|path> or --largest")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--project", help="project id, name or a path inside the repo")
    ap.add_argument("--largest", action="store_true", help="use the registered project with the biggest index.db")
    ap.add_argument("--repeat", type=int, default=5)
    ap.add_argument("--samples", type=int, default=25, help="node pairs / seeds per timed operation")
    ap.add_argument("--seed", type=int, default=7)
    ap.add_argument("--json", type=Path, help="also write the results here")
    args = ap.parse_args()

    project = _pick_project(args.project, args.largest)
    store = GraphStore(project.id)
    db_file = db_path_for_project(project.id)

    def cold_load() -> GraphIndex:
        return GraphIndex.build(store.list_all_nodes(), store.list_edges())

    results: dict[str, object] = {"project": project.name, "db_mb": round(db_file.stat().st_size / 1e6, 1)}
    results["load_index_cold"] = _ms(cold_load, max(1, min(args.repeat, 3)))
    dbmod._INDEX_CACHE.clear()
    store.load_index()
    results["load_index_cached"] = _ms(store.load_index, args.repeat)

    index = store.load_index()
    dep_edges = sum(1 for e in index.edges if e.edge_type in DEPENDENCY_EDGES)
    results["nodes"], results["edges"], results["dependency_edges"] = len(index.nodes), len(index.edges), dep_edges

    rng = random.Random(args.seed)
    code = sorted(
        (n.id for n in index.nodes.values() if n.node_type in (NodeType.FUNCTION, NodeType.CLASS, NodeType.MODULE)),
    )
    if len(code) < 2:
        sys.exit("project has too few code nodes to benchmark")
    pairs = [(rng.choice(code), rng.choice(code)) for _ in range(args.samples)]
    seeds = sorted(code, key=lambda i: (-index.fan_in(i), i))[: args.samples]

    results["find_path"] = _ms(lambda: [find_path(index, a, b) for a, b in pairs], args.repeat)
    results["find_path"]["per_call_ms"] = round(results["find_path"]["median_ms"] / len(pairs), 3)
    results["impact_depth3"] = _ms(lambda: [compute_impact(index, [s]) for s in seeds], args.repeat)
    results["impact_depth3"]["per_call_ms"] = round(results["impact_depth3"]["median_ms"] / len(seeds), 3)
    results["neighborhood_depth3"] = _ms(lambda: [neighborhood_subgraph(index, s, depth=3) for s in seeds], args.repeat)
    results["neighborhood_depth3"]["per_call_ms"] = round(results["neighborhood_depth3"]["median_ms"] / len(seeds), 3)

    try:  # present once the facade exists
        from ci_core import graph_algo
    except ImportError:
        graph_algo = None
    if graph_algo is not None:
        results["graph_backend"] = graph_algo.backend_name()
        results["scc_dependency_graph"] = _ms(lambda: graph_algo.strongly_connected_components(index), args.repeat)
        results["cycles"] = len(graph_algo.dependency_cycles(index))

    print(
        f"project {results['project']}  db {results['db_mb']} MB  nodes {results['nodes']}  "
        f"edges {results['edges']}  dependency edges {dep_edges}"
    )
    for key, val in results.items():
        if isinstance(val, dict):
            extra = f"  ({val['per_call_ms']} ms/call)" if "per_call_ms" in val else ""
            print(f"  {key:<22} median {val['median_ms']:>9} ms   max {val['max_ms']:>9} ms{extra}")
    if "graph_backend" in results:
        print(f"  graph backend: {results['graph_backend']}   cycles found: {results['cycles']}")
    if args.json:
        args.json.write_text(json.dumps(results, indent=2), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
