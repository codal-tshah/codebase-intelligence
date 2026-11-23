# Data model

*Last verified against code: `backend/packages/core/src/ci_core/models.py`, `db.py`, `insights.py`, `backend/packages/parsers/src/ci_parsers/python_parser.py`.*

## Node types (`NodeType`)

`Project`, `Package`, `Module`, `Class`, `Function`, `Endpoint`, `Middleware`, `Component`, `Model`, `Table`, `Field`, `Migration`, `ExternalService`, `ConfigRef`.

## Edge types (`EdgeType`)

`CONTAINS`, `IMPORTS`, `CALLS`, `ROUTES_TO`, `HANDLES`, `READS_MODEL`, `WRITES_MODEL`, `FK_TO`, `QUERIES`, `DEPENDS_ON`, `SUBSCRIBES`, `MIDDLEWARE`, `RENDERS`, `HTTP_CALLS`, `INJECTS`.

## Dependency subgraph

`DEPENDENCY_EDGES` in `insights.py` includes `CALLS`, `IMPORTS`, `ROUTES_TO`, model access, `FK_TO`, `DEPENDS_ON`, `SUBSCRIBES`, `QUERIES`, `RENDERS`, `HTTP_CALLS`, `INJECTS` — used for impact, path, neighborhood, suggestions. `CONTAINS` is hierarchy, not a dependency edge for those algorithms.

## Properties (common keys)

| Key | Meaning |
| --- | --- |
| `layer` | Architectural layer id (`ci_core.layers`) |
| `role` | Framework role (e.g. urls, models, service) |
| `import_kind` | On `IMPORTS`: `type_only` or `lazy` |
| `has_runtime_import` | Merged edge still has a load-time import |
| `subpackage` | Package node marker |
| `namespace` | Package for a folder without `__init__.py` (≥2 indexed modules) |
| `field_count` | On **Model** in the ER view: total fields in the index when the diagram shows ≤12 |
| `summary`, `tags`, `complexity` | UI / search metadata |

Verify per-extractor in adapter code before documenting new keys.

## Stable ids

`stable_node_id(project_id, *parts)` — SHA-256 hex truncated to 32 chars (`python_parser.py`).

## SQLite (`index.db` per project)

Tables in `ci_core.db`: `projects`, `nodes`, `edges`, `jobs`, `chunks`, `llm_requests`. JSON in `properties_json` / `metadata_json`. Path: `get_settings().data_dir / "projects" / project_id / "index.db"`.

## GraphIndex

Built via `GraphIndex.build(nodes, edges)`:

- `nodes: dict[id, NodeRecord]`
- `edges: list[EdgeRecord]`
- `outgoing` / `incoming` adjacency lists

Loaded through `GraphStore.load_index()` with process-level cache keyed by DB file mtime + size.

## Other data-dir files

Per project: fingerprints, settings, saved views, `index.lock`. Global: `audit.jsonl` at data dir root (`ci_core.audit`).
