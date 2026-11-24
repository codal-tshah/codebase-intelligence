# Data model

*Last verified against code: `backend/packages/core/src/ci_core/models.py`, `db.py`, `insights.py`, `backend/packages/core/src/ci_core/evidence.py`, `backend/packages/parsers/src/ci_parsers/python_parser.py`.*

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
| `match_variant` | On `http_calls[]` entries and `HTTP_CALLS` / some `DEPENDS_ON` edges from `link_http_calls`: `literal`, `proxy_prefix`, `external`, or `unresolved` |
| `http_calls[]` | On client nodes: static outbound HTTP metadata (`url`, `method`, `line`, optional `endpoint_id`, `match_variant`) |
| `aggregated` | Explore roll-up edges (`weight`, `by_type`) |

Verify per-extractor in adapter code before documenting new keys.

## Evidence (read-time, not stored on edges)

`ci_core.evidence.classify_node`, `classify_edge`, and `classify_http_call_record` produce a deterministic `evidence` object:

| Field | Meaning |
| --- | --- |
| `tier` | `high`, `medium`, `low`, or `unknown` — qualitative reliability, not a rescaling of `confidence` |
| `reason_code` | Stable id (e.g. `static_import`, `http_literal_route_match`, `http_proxy_prefix_match`, `unresolved_http`, `aggregated_relationship`) |
| `reason` | Short human-readable line for UI and agents |

Rules use `edge_type`, `extractor`, edge/node `properties` (`import_kind`, `match_variant`, `inferred`, …), and conservative confidence bands — never tier from a lone float. Indexes without `match_variant` still classify HTTP via legacy linker heuristics. Unresolved calls stay on the source node as `http_calls[]` with `match_variant: unresolved`; no synthetic `HTTP_CALLS` edge is created.

API graph views, `GET .../nodes/{id}`, `GET .../graph/neighborhood`, `GET .../path`, MCP `get_node` / `find_references` / `trace_endpoint` chain hops / `build_context` callers·callees·models, and `ci export` attach `evidence` at serialization time (no new SQLite columns).

**Limits:** Impact and suggestion payloads still omit per-edge evidence. Canvas dashed styling remains tied to the **0.7** `confidence` threshold, not evidence tier.

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
