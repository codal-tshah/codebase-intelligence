/**
 * Explore expand state: reducer only — no setState inside other updaters (StrictMode-safe).
 */

export type ExploreHistorySnap = { expanded: string[]; childOffsets: Record<string, number> };

export type ExploreState = {
  expanded: string[];
  /** Paging offsets for structural children per expanded node (matches API extra_child_offsets). */
  childOffsets: Record<string, number>;
  history: ExploreHistorySnap[];
};

export type ExploreAction =
  | { type: "toggle"; id: string }
  | { type: "set"; expanded: string[]; childOffsets?: Record<string, number> }
  | { type: "expandPath"; ancestors: string[] }
  | { type: "collapseToLevel"; level: number; orderedAncestors: string[] }
  | { type: "expandAll"; rootId: string; depthLimit: number }
  | { type: "expandChildren"; ids: string[] }
  | { type: "loadMoreChildren"; nodeId: string; delta?: number }
  | { type: "back" }
  | { type: "reset" }
  | { type: "clearExplore" };

const MAX_HISTORY = 20;

export function uniqExpanded(ids: string[]): string[] {
  return [...new Set(ids.filter(Boolean))].sort((a, b) => a.localeCompare(b));
}

function snap(s: ExploreState): ExploreHistorySnap {
  return { expanded: [...s.expanded], childOffsets: { ...s.childOffsets } };
}

function pushHistory(prev: ExploreState): ExploreState {
  return {
    ...prev,
    history: [...prev.history, snap(prev)].slice(-MAX_HISTORY),
  };
}

export function exploreReducer(state: ExploreState, action: ExploreAction): ExploreState {
  switch (action.type) {
    case "toggle": {
      const has = state.expanded.includes(action.id);
      const nextExp = has ? state.expanded.filter((x) => x !== action.id) : [...state.expanded, action.id];
      let childOffsets = { ...state.childOffsets };
      if (has) {
        delete childOffsets[action.id];
      }
      const base = pushHistory(state);
      return {
        ...base,
        expanded: uniqExpanded(nextExp),
        childOffsets,
      };
    }
    case "set": {
      const base = pushHistory(state);
      return {
        ...base,
        expanded: uniqExpanded(action.expanded),
        childOffsets: action.childOffsets ? { ...action.childOffsets } : { ...state.childOffsets },
      };
    }
    case "expandPath": {
      const base = pushHistory(state);
      return {
        ...base,
        expanded: uniqExpanded([...action.ancestors, ...state.expanded]),
        childOffsets: { ...state.childOffsets },
      };
    }
    case "collapseToLevel": {
      const keep = action.orderedAncestors.slice(0, Math.max(0, action.level));
      const base = pushHistory(state);
      const nextOffsets: Record<string, number> = {};
      for (const k of Object.keys(state.childOffsets)) {
        if (keep.includes(k)) nextOffsets[k] = state.childOffsets[k]!;
      }
      return {
        ...base,
        expanded: uniqExpanded(keep),
        childOffsets: nextOffsets,
      };
    }
    case "expandAll": {
      if (state.expanded.includes(action.rootId)) return state;
      const base = pushHistory(state);
      return {
        ...base,
        expanded: uniqExpanded([...state.expanded, action.rootId]),
        childOffsets: { ...state.childOffsets },
      };
    }
    case "expandChildren": {
      const base = pushHistory(state);
      return {
        ...base,
        expanded: uniqExpanded([...state.expanded, ...action.ids]),
        childOffsets: { ...state.childOffsets },
      };
    }
    case "loadMoreChildren": {
      const base = pushHistory(state);
      const delta = action.delta ?? 80;
      const cur = state.childOffsets[action.nodeId] ?? 0;
      return {
        ...base,
        expanded: [...state.expanded],
        childOffsets: { ...state.childOffsets, [action.nodeId]: cur + delta },
      };
    }
    case "back": {
      if (!state.history.length) return state;
      const prev = state.history[state.history.length - 1]!;
      return {
        expanded: [...prev.expanded],
        childOffsets: { ...prev.childOffsets },
        history: state.history.slice(0, -1),
      };
    }
    case "reset": {
      const base = pushHistory(state);
      return {
        expanded: [],
        childOffsets: {},
        history: base.history,
      };
    }
    case "clearExplore":
      return {
        expanded: [],
        childOffsets: {},
        history: [],
      };
    default:
      return state;
  }
}

export function createExploreState(
  expanded: string[] = [],
  childOffsets: Record<string, number> = {},
): ExploreState {
  return { expanded: uniqExpanded(expanded), childOffsets: { ...childOffsets }, history: [] };
}

export function expandedKey(ids: string[]): string {
  return [...ids].sort((a, b) => a.localeCompare(b)).join(",");
}
