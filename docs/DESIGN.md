# Design system

The dashboard design system lives in `frontend/src/styles.css`, with graph colours in `frontend/src/graphTheme.ts` and icons in `frontend/src/icons.tsx`. This pass refined it rather than replacing it. Everything below is implemented; nothing here is aspirational unless marked **planned**.

## Principles

- **Look:** warm paper (`--bg #F7F6F2`), ink text (`--text #1D1C19`), and **one** teal accent (`--accent #1F5C56`).
  - Hierarchy comes from type and spacing, not from boxes and colour.
  - No gradients, glows, sparkle or emoji icons.
- **Type:** Schibsted Grotesk (UI), Newsreader (display), IBM Plex Mono (code and paths).
  - Fonts are **bundled** via `@fontsource` packages, so there are no CDN requests (see [DECISIONS.md](DECISIONS.md)).
- **Spacing and shape:** 4px spacing scale (`--s1`…`--s7`), 1px dividers, 6–8px radii.
- **Motion:** 150ms or 200ms with `--ease`. `prefers-reduced-motion` disables animation and camera easing.

## Node-type tints

Each node card gets its layer colour as `--layer`. The card derives three things from it:

| Part | Rule | Token |
|---|---|---|
| Fill | 7% layer over `--surface` | `--tint-fill` |
| Border | 35% layer over `--divider` | `--tint-border` |
| Layer label text | 72% layer + 28% `--text` | `--tint-label` |
| Left tick | 100% layer, 3px | n/a |

| Node type | Colour | Source |
|---|---|---|
| API / route | blue-grey `#55708F` | layer `api` |
| Service | green `#3E7770` | layer `service` |
| Middleware | olive `#6F7A45` | layer `middleware` |
| Data / model | amber `#9C7A3C` | layer `data` |
| External service | mauve `#7D6178` | layer `external` |
| UI | clay `#A15E45` | layer `ui` |
| Queue / job | rose `#9A5466` (`JOB_COLOR`) | any node with `properties.job` |
| Config / test (decision grey) | grey `#8A867C` | layers `config`, `test` |
| Error | red `#A1412E` (`--error`) | Used for writes and impact "changed". **No node type is tinted red yet:** no analyzer emits error nodes. |

Type is never shown by colour alone. Every card also shows the **type icon** (Lucide) and the **type name**, plus the layer name.

## Contrast (WCAG 2.2 AA)

Computed with the WCAG relative-luminance formula from the token values. The same values are enforced in the browser by the axe check in `frontend/e2e/a11y-offline.spec.ts`. Two tokens were darkened in this pass so that every pair passes:

- `--text-3`: `#716d63` → `#6b675d`. It was 4.41:1 on `--sunken`.
- `--warning`: `#94671e` → `#8a5f1c`. It was 4.24:1 on `--warning-soft`.

### Base tokens

| Foreground | Background | Ratio | AA (4.5:1) |
|---|---|---|---|
| `--text` #1d1c19 | `--bg` #f7f6f2 | 15.76 | ✅ |
| `--text` #1d1c19 | `--surface` #fcfbf8 | 16.47 | ✅ |
| `--text` #1d1c19 | `--sunken` #efede7 | 14.56 | ✅ |
| `--text-2` #55524a | `--bg` #f7f6f2 | 7.21 | ✅ |
| `--text-2` #55524a | `--sunken` #efede7 | 6.66 | ✅ |
| `--text-3` #6b675d | `--bg` #f7f6f2 | 5.22 | ✅ |
| `--text-3` #6b675d | `--surface` #fcfbf8 | 5.45 | ✅ |
| `--text-3` #6b675d | `--sunken` #efede7 | 4.82 | ✅ |
| `--text-3` #6b675d | `--accent-soft` #e4eeeb | 4.76 | ✅ |
| `--accent` #1f5c56 | `--bg` #f7f6f2 | 7.13 | ✅ |
| `--on-accent` #ffffff | `--accent` #1f5c56 | 7.71 | ✅ |
| `--text` #1d1c19 | `--accent-soft (selected)` #e4eeeb | 14.39 | ✅ |
| `--error` #a1412e | `--surface` #fcfbf8 | 6.13 | ✅ |
| `--warning` #8a5f1c | `--warning-soft` #f4ecdd | 4.79 | ✅ |
| `--success` #3d7550 | `--surface` #fcfbf8 | 5.26 | ✅ |

### Node tints (fill = 7% layer over surface; label = 72% layer + 28% text)

| Node type | Layer colour | Fill | Name (`--text`) | Meta (`--text-3`) | Layer label | Raw layer colour as text (not used) |
|---|---|---|---|---|---|---|
| API / route | #55708F | #f0f1f1 | 15.1 ✅ | 4.98 ✅ | #45586e 6.5 ✅ | 4.5 ✅ |
| Middleware | #6F7A45 | #f2f2eb | 15.2 ✅ | 5.02 ✅ | #586039 5.9 ✅ | 4.1 ❌ |
| Service | #3E7770 | #eff2ee | 15.1 ✅ | 5.00 ✅ | #355e58 6.4 ✅ | 4.6 ✅ |
| Data / model | #9C7A3C | #f5f2eb | 15.2 ✅ | 5.04 ✅ | #786032 5.3 ✅ | 3.6 ❌ |
| UI | #A15E45 | #f6f0eb | 15.1 ✅ | 4.99 ✅ | #7c4c39 6.3 ✅ | 4.4 ❌ |
| External | #7D6178 | #f3f0ef | 15.0 ✅ | 4.97 ✅ | #624e5d 6.7 ✅ | 4.8 ✅ |
| Queue / job | #9A5466 | #f5efee | 15.0 ✅ | 4.96 ✅ | #774450 6.8 ✅ | 4.8 ✅ |
| Config / test (decision grey) | #8A867C | #f4f3ef | 15.3 ✅ | 5.08 ✅ | #6b6860 5.0 ✅ | 3.3 ❌ |
| Error | #A1412E | #f6eeea | 14.9 ✅ | 4.92 ✅ | #7c3728 7.5 ✅ | 5.5 ✅ |

### Non-text (WCAG 1.4.11, 3:1)

| Element | Against | Ratio | 3:1 |
|---|---|---|---|
| Selected border/bar --accent | #fcfbf8 | 7.45 | ✅ |
| Focus ring --accent | #f7f6f2 | 7.13 | ✅ |
| Selected border vs accent-soft fill | #e4eeeb | 6.51 | ✅ |

The last column shows why layer labels use the darkened mix: four raw layer colours fail as text.

**Dimmed nodes** (focus mode, opacity 0.45) are intentionally below AA: they are de-emphasised context, not content. To read them at full contrast, clear the selection or turn focus mode off (toolbar toggle).

## Selection, focus, hover

| State | Treatment | Not colour-only because |
|---|---|---|
| Hover | Border darkens toward the layer colour | n/a |
| Selected | `--accent-soft` fill, accent border plus 1px inset (2px total, no layout shift), 4px accent left bar, faint outer ring | The border weight and the bar change, not just the hue |
| Neighbour of selection | Border and ring in blue-grey | n/a |
| Keyboard focus | 2px accent outline, 3px offset, on the focused node (React Flow wrapper) and on every control (`:focus-visible`) | Outline |
| Inferred (confidence < 0.7) | Dashed border plus an "inferred" label | Dash pattern plus text |
| Layer filter on/off | `aria-pressed`, strike-through and faded dot when hidden | Strike-through plus ARIA |

## Graph mapping

- **Legend:** the layer legend doubles as a filter. A new edge legend covers solid vs dashed lines, inferred edges, HTTP edges and inferred nodes.
- **Breadcrumbs (Explore):** shown on the canvas, top-left, so the toolbar stays one row. Clicking a crumb collapses the tree below it.
- **Focus mode:** toolbar toggle, default on, remembered per browser.
  - Selecting a node fades unrelated nodes to 0.45.
  - It never fades the selection's own subtree or its ancestors.
  - Turning it off keeps the neighbour highlight without fading anything.
- **Semantic zoom:** the `graph-pane` gets a `zoom-far`, `zoom-mid` or `zoom-near` class. It re-renders only when the level changes.
  - **far (< 0.5):** names only, at 28px, so they stay legible zoomed out. Edge labels and arrowheads are hidden.
  - **mid (0.5–0.9):** helper text hidden.
  - **near:** full cards.
- **Explore groups:** a single-row title (icon, name, type · child count, chevron) reserves `GROUP_TITLE = 52px`. A unit test checks that children never overlap the title and never leave the parent box, at 4 levels of nesting.
- **CONTAINS edges:** hidden when the child is nested inside its parent. Nesting already shows containment.

## Screen states

| State | Where |
|---|---|
| Loading | Skeleton nodes on the canvas; skeleton overview; loading dot on the Explore node being expanded |
| Empty | "Nothing to show here yet" on the canvas; "No repository yet" in the sidebar; empty files and childless packages in the Inspector |
| Error | Canvas error with *Try again*; ingest errors (including git clone and access failures) in an `role="alert"` message; export errors in the menu |
| Stale | Freshness banner (files changed since the last index) with *Re-index* and *Impact of changes* |
| Unauthorised (server mode) | API-key dialog |

## Dark theme

**Planned.** Graph colours are still TypeScript constants (`graphTheme.ts`), not CSS tokens. Moving them to tokens comes first so dark mode can come from the same token set.
