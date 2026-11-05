from __future__ import annotations

import hashlib
import json
from pathlib import Path

from ci_ai.chunking import split_text
from ci_core.db import GraphStore, new_id
from ci_core.models import NodeRecord, NodeType
from ci_security import sanitize_for_llm

MODULE_HEAD_LINES = 80
SYMBOL_TYPES = (NodeType.FUNCTION, NodeType.CLASS, NodeType.MODEL, NodeType.MIDDLEWARE, NodeType.COMPONENT)


def _hash_embed(text: str, dims: int = 256) -> list[float]:
    """Deterministic local embedding so the product works without any external API."""
    vec = [0.0] * dims
    for tok in text.lower().replace("_", " ").replace(".", " ").split():
        h = int(hashlib.sha256(tok.encode()).hexdigest(), 16)
        vec[h % dims] += 1.0
    norm = sum(v * v for v in vec) ** 0.5 or 1.0
    return [v / norm for v in vec]


def _chunk(node: NodeRecord | None, rel: str, start: int, end: int, code: str, meta: dict) -> dict:
    safe, _ = sanitize_for_llm(code)
    # Summary/tags/role are embedded with the code so "who handles login" finds the right view.
    context = ""
    if node is not None:
        props = node.properties
        context = " ".join(
            str(x) for x in (node.name, props.get("role"), props.get("summary"), " ".join(props.get("tags", []))) if x
        )
    return {
        "id": new_id(),
        "node_id": node.id if node else None,
        "source_path": rel,
        "start_line": start,
        "end_line": end,
        "content": safe,
        "embedding_json": json.dumps(_hash_embed(f"{context}\n{safe}")),
        "metadata": meta,
    }


def embed_project_chunks(project_id: str, root: Path, only_paths: set[str] | None = None) -> int:
    """Chunk and embed source files. Returns the number of chunks written.

    Callers re-embedding existing paths must `store.delete_chunks(paths)` first.
    """
    store = GraphStore(project_id)
    by_start: dict[tuple[str, int], NodeRecord] = {}
    module_nodes: dict[str, NodeRecord] = {}
    for n in store.list_all_nodes():
        if not n.source_path:
            continue
        if n.node_type in (NodeType.MODULE, NodeType.MIGRATION):
            module_nodes[n.source_path] = n
        elif n.node_type in SYMBOL_TYPES and n.start_line:
            by_start[(n.source_path, n.start_line)] = n

    chunks: list[dict] = []
    # Embed exactly what the analyzers indexed (any language), never unindexed files.
    for rel in sorted(module_nodes):
        if only_paths is not None and rel not in only_paths:
            continue
        src_file = root / rel
        if not src_file.is_file():
            continue
        source = src_file.read_text(encoding="utf-8", errors="replace")
        lines = source.splitlines()
        if not lines:
            continue

        symbol_nodes = sorted(
            (n for (path, _), n in by_start.items() if path == rel), key=lambda n: n.start_line or 0
        )
        mod_node = module_nodes.get(rel)
        head_end = min(len(lines), MODULE_HEAD_LINES)
        chunks.append(
            _chunk(
                mod_node, rel, 1, head_end, "\n".join(lines[:head_end]), {"kind": "module-head", "path": rel}
            )
        )
        for node in symbol_nodes:
            start, end = node.start_line or 1, node.end_line or node.start_line or 1
            chunks.append(
                _chunk(
                    node,
                    rel,
                    start,
                    end,
                    "\n".join(lines[start - 1 : end]),
                    {"qualified_name": node.qualified_name, "kind": node.node_type.value},
                )
            )
        if not symbol_nodes and len(lines) > head_end:
            cursor = 0
            for i, piece in enumerate(split_text(source, src_file.suffix)):
                idx = source.find(piece[:120], cursor)
                if idx < 0:
                    idx = cursor
                cursor = max(idx, cursor)
                start = source.count("\n", 0, idx) + 1
                end = start + piece.count("\n")
                chunks.append(
                    _chunk(mod_node, rel, start, end, piece, {"chunk_index": i, "split": "language-aware"})
                )
    if chunks:
        store.upsert_chunks(chunks)
    return len(chunks)


def embed_query(text: str) -> list[float]:
    safe, _ = sanitize_for_llm(text)
    return _hash_embed(safe)
