# User guide

For people reading a codebase in the dashboard. Setup is in the [README](../README.md#quickstart). Screenshots are in [`ui-review/after/`](ui-review/after/): the fullstack fixture, and NetBox (18.7k nodes) as a large repo.

## 1. Add a repository

Click **+** (top bar), then paste a GitHub URL or an absolute local path, then **Analyze**.

- GitHub URLs are checked as you type (*Reachable · default branch …*), and *Analyze* stays disabled until access works.
- Private repos need `CI_GITHUB_TOKEN` on the server ([private-repos.md](private-repos.md)).
- Clone and index failures appear under the field with the reason.

![Ingest](ui-review/after/ingest.png)

## 2. Find your way around

| Area | What it does |
|---|---|
| Sidebar | Diagrams available for this project, with counts. The **Layers** list doubles as a filter (click to hide or show a layer). **Edges** explains line styles. |
| Overview | Project name, key numbers, and where to start. *Details* expands the summary (compact automatically in Explore). |
| Toolbar | View title, **Filter diagram**, Explore controls, **Focus mode** (fade unrelated nodes), reload, show or hide the details pane. |
| Canvas | Two-finger scroll pans; pinch (or ⌘/Ctrl + wheel) zooms. Minimap and zoom controls bottom-left and bottom-right. |
| Details pane | **Details** (selected node or edge), **Routes**, **Ask**, plus **Tour**, **Impact**, **Path** and **Improve**. Drag its edge to resize; ⌘\\ toggles it. |

**Reading a card:**
- the type icon and type name, plus its layer (API, Service, Data…)
- a soft tint in the layer's colour
- *N in* = how many things depend on it
- dashed outline and *inferred* = found by heuristics, so check the source

Zoomed out, cards show names only so they stay readable; zoom in for full cards.

![API flow with a selection](ui-review/after/fullstack-select-node.png)

## 3. Explore a large codebase

**Explore** starts at top-level packages.

- Click the **chevron** to expand a package in place; its children appear inside it. Click again to collapse.
- **Double-click** zooms to a node.
- **Breadcrumbs** (top-left of the canvas) show where the selection sits; click one to collapse back to that level.
- **←** undoes the last expand. **«** resets to the top. **Collapse to** jumps to a level.
- **+** expands the selected node. **Depth** sets how far the neighbourhood highlight reaches.
- Click an **edge** to see what it aggregates (for example *calls ×12*) and the underlying relations.
- Selecting a package lists its children in Details.

![Explore, nested](ui-review/after/fullstack-explore-expanded.png)

## 4. Search and keyboard

| Key | Action |
|---|---|
| ⌘K or `/` | Search code, views and actions |
| ⌘J | Ask |
| ⌘\\ | Toggle the details pane |
| Tab, Enter | Move focus between graph nodes; Enter opens the focused node |
| Esc | Clear impact, path or highlight overlays; close menus |

## 5. Ask, Tour, Impact, Path, Improve

- **Ask:** questions about the code. Answers cite nodes (click to jump) and `file:line` (opens the source). Works without an LLM (graph tools only). With `ALLOW_LLM=1` it uses your configured model.
- **Tour:** a guided reading order from entry points to data.
- **Impact:** what a change to the selected node, or to your uncommitted changes, could affect, coloured by hops.
- **Path:** the shortest dependency path between two nodes.
- **Improve:** refactoring and reuse leads from static heuristics:
  - hotspots (many dependants)
  - large functions
  - helpers duplicated across files
  - models written from many places
  - import cycles
  - possibly unused functions

  Filter by kind; click a node to open it. Each kind gets a share of the list, so on large repos hotspots don't crowd out the rest. These are leads, not verdicts: dynamic calls can be missed.

![Improve tab](ui-review/after/tab-improve.png)

## 6. Share and export

- **Copy link** (chain icon): the URL keeps project, view, selection and Explore expansion. Pasting it into an open tab navigates there.
- **Export** (download icon) for the current view:

  | Format | Use it for |
  |---|---|
  | SVG, PNG | Slides, tickets |
  | Mermaid | GitHub, GitLab, Notion |
  | Markdown | Diagram plus node and relation tables, for PRs and wikis |
  | JSON | This view |
  | Full graph as JSON | Everything |

  All are generated in the browser.

![Export menu](ui-review/after/fullstack-export-menu.png)

## 7. Stale data

When files have changed since the last index, a banner offers **Re-index** (incremental) and **Impact of changes**.

## 8. Shared server (server mode)

If your admin runs `CI_MODE=server`, the dashboard asks for the API key once per browser tab. It is kept for that tab only.

![API key prompt](ui-review/after/server-mode-api-key.png)
