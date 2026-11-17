/**
 * One popover pattern for every dropdown, menu and listbox in the dashboard.
 *
 * - Rendered in a portal on `document.body`, so no `overflow: hidden` ancestor (toolbar, canvas,
 *   side panels) and no React Flow stacking context can clip it.
 * - Anchored with `position: fixed` to its trigger; flips above when there is no room below and
 *   shifts horizontally to stay inside the viewport; height is capped to the free space and scrolls.
 * - Esc and outside clicks close it and focus returns to the trigger; arrow keys, Home/End and
 *   type-ahead move between items.
 */
import { ChevronDown } from "lucide-react";
import {
  useCallback,
  useEffect,
  useId,
  useLayoutEffect,
  useRef,
  useState,
  type CSSProperties,
  type KeyboardEvent as ReactKeyboardEvent,
  type ReactNode,
  type RefObject,
} from "react";
import { createPortal } from "react-dom";

const GAP = 4;
const MARGIN = 8;

export type Placement = "bottom-start" | "bottom-end";

/** Pure placement maths (unit-tested): where a popover of `size` goes next to `anchor`. */
export function computePopoverPosition(
  anchor: { top: number; bottom: number; left: number; right: number; width: number },
  size: { width: number; height: number },
  viewport: { width: number; height: number },
  placement: Placement = "bottom-start",
): { top: number; left: number; maxHeight: number; flipped: boolean } {
  const below = viewport.height - anchor.bottom - GAP - MARGIN;
  const above = anchor.top - GAP - MARGIN;
  const flipped = size.height > below && above > below;
  const room = Math.max(120, flipped ? above : below);
  const height = Math.min(size.height, room);
  const top = flipped ? anchor.top - GAP - height : anchor.bottom + GAP;
  let left = placement === "bottom-end" ? anchor.right - size.width : anchor.left;
  left = Math.min(left, viewport.width - MARGIN - size.width);
  left = Math.max(MARGIN, left);
  return { top: Math.max(MARGIN, top), left, maxHeight: room, flipped };
}

type PopoverProps = {
  open: boolean;
  onClose: (opts?: { returnFocus?: boolean }) => void;
  anchorRef: RefObject<HTMLElement | null>;
  placement?: Placement;
  /** Match the trigger's width (selects). */
  matchWidth?: boolean;
  className?: string;
  role?: "menu" | "listbox" | "dialog";
  id?: string;
  label?: string;
  children: ReactNode;
  onKeyDown?: (e: ReactKeyboardEvent<HTMLDivElement>) => void;
};

export function Popover({
  open,
  onClose,
  anchorRef,
  placement = "bottom-start",
  matchWidth,
  className,
  role,
  id,
  label,
  children,
  onKeyDown,
}: PopoverProps) {
  const ref = useRef<HTMLDivElement>(null);
  const [style, setStyle] = useState<CSSProperties>({ position: "fixed", top: -9999, left: -9999 });

  const place = useCallback(() => {
    const anchor = anchorRef.current;
    const el = ref.current;
    if (!anchor || !el) return;
    const a = anchor.getBoundingClientRect();
    // Measure natural size without the previous max-height cap.
    el.style.maxHeight = "none";
    const minWidth = matchWidth ? a.width : 0;
    const width = Math.max(el.offsetWidth, minWidth);
    const pos = computePopoverPosition(a, { width, height: el.scrollHeight }, { width: window.innerWidth, height: window.innerHeight }, placement);
    el.style.maxHeight = `${pos.maxHeight}px`;
    setStyle((prev) =>
      prev.top === pos.top && prev.left === pos.left && prev.maxHeight === pos.maxHeight && prev.minWidth === (minWidth || undefined)
        ? prev
        : { position: "fixed", top: pos.top, left: pos.left, maxHeight: pos.maxHeight, minWidth: minWidth || undefined },
    );
  }, [anchorRef, matchWidth, placement]);

  useLayoutEffect(() => {
    if (!open) return;
    place();
  }, [open, place, children]);

  useEffect(() => {
    if (!open) return;
    const onScroll = () => place();
    const onDown = (e: MouseEvent) => {
      const t = e.target as Node;
      if (ref.current?.contains(t) || anchorRef.current?.contains(t)) return;
      onClose({ returnFocus: false });
    };
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        e.stopPropagation();
        onClose({ returnFocus: true });
      }
    };
    window.addEventListener("resize", onScroll);
    window.addEventListener("scroll", onScroll, true);
    document.addEventListener("mousedown", onDown);
    document.addEventListener("keydown", onKey, true);
    return () => {
      window.removeEventListener("resize", onScroll);
      window.removeEventListener("scroll", onScroll, true);
      document.removeEventListener("mousedown", onDown);
      document.removeEventListener("keydown", onKey, true);
    };
  }, [open, place, onClose, anchorRef]);

  if (!open) return null;
  return createPortal(
    <div
      ref={ref}
      id={id}
      role={role}
      aria-label={label}
      className={`popover ${className ?? ""}`}
      style={style}
      onKeyDown={onKeyDown}
    >
      {children}
    </div>,
    document.body,
  );
}

/** Roving focus inside a popover: arrows / Home / End / type-ahead over `[data-pop-item]`. */
export function usePopoverKeys(containerSelector = "[data-pop-item]:not([disabled])") {
  return (e: ReactKeyboardEvent<HTMLElement>) => {
    const root = e.currentTarget as HTMLElement;
    const items = [...root.querySelectorAll<HTMLElement>(containerSelector)];
    if (!items.length) return;
    const i = items.indexOf(document.activeElement as HTMLElement);
    let next = -1;
    if (e.key === "ArrowDown") next = i < 0 ? 0 : (i + 1) % items.length;
    else if (e.key === "ArrowUp") next = i < 0 ? items.length - 1 : (i - 1 + items.length) % items.length;
    else if (e.key === "Home") next = 0;
    else if (e.key === "End") next = items.length - 1;
    else if (e.key.length === 1 && /\S/.test(e.key)) {
      const k = e.key.toLowerCase();
      const start = i + 1;
      const order = [...items.slice(start), ...items.slice(0, start)];
      const hit = order.find((el) => (el.textContent ?? "").trim().toLowerCase().startsWith(k));
      if (hit) next = items.indexOf(hit);
    } else if (e.key === "Tab") {
      return;
    }
    if (next >= 0) {
      e.preventDefault();
      items[next]!.focus();
    }
  };
}

// ------------------------------------------------------------------ select (listbox)

export type SelectOption<T extends string | number> = { value: T; label: string; hint?: string; disabled?: boolean };

type MenuSelectProps<T extends string | number> = {
  value: T | null;
  options: SelectOption<T>[];
  onChange: (value: T) => void;
  /** Accessible name of the control (also shown as the trigger text when nothing is chosen). */
  label: string;
  placeholder?: string;
  className?: string;
  disabled?: boolean;
  title?: string;
};

/** Drop-in replacement for a native `<select>` that never gets clipped and matches the theme. */
export function MenuSelect<T extends string | number>({
  value,
  options,
  onChange,
  label,
  placeholder,
  className,
  disabled,
  title,
}: MenuSelectProps<T>) {
  const [open, setOpen] = useState(false);
  const trigger = useRef<HTMLButtonElement>(null);
  const listId = useId();
  const keys = usePopoverKeys();
  const current = options.find((o) => o.value === value);

  const close = useCallback((opts?: { returnFocus?: boolean }) => {
    setOpen(false);
    if (opts?.returnFocus !== false) trigger.current?.focus();
  }, []);

  // Focus the chosen option (or the first) when the list opens.
  useEffect(() => {
    if (!open) return;
    const t = setTimeout(() => {
      const list = document.getElementById(listId);
      const el = list?.querySelector<HTMLElement>('[aria-selected="true"]') ?? list?.querySelector<HTMLElement>("[data-pop-item]");
      el?.focus();
    }, 0);
    return () => clearTimeout(t);
  }, [open, listId]);

  return (
    <>
      <button
        ref={trigger}
        type="button"
        className={`menu-select ${className ?? ""}`}
        aria-haspopup="listbox"
        aria-expanded={open}
        aria-controls={open ? listId : undefined}
        aria-label={`${label}: ${current?.label ?? placeholder ?? "none"}`}
        title={title}
        disabled={disabled}
        onClick={() => setOpen((o) => !o)}
        onKeyDown={(e) => {
          if (e.key === "ArrowDown" || e.key === "ArrowUp") {
            e.preventDefault();
            setOpen(true);
          }
        }}
      >
        <span className="menu-select-value">{current?.label ?? placeholder ?? label}</span>
        <ChevronDown size={14} strokeWidth={1.5} aria-hidden />
      </button>
      <Popover open={open} onClose={close} anchorRef={trigger} matchWidth role="listbox" id={listId} label={label} onKeyDown={keys}>
        {options.map((o) => (
          <button
            key={String(o.value)}
            type="button"
            role="option"
            data-pop-item
            aria-selected={o.value === value}
            disabled={o.disabled}
            className="popover-item"
            onClick={() => {
              onChange(o.value);
              close();
            }}
          >
            <span>{o.label}</span>
            {o.hint ? <span className="muted popover-hint">{o.hint}</span> : null}
          </button>
        ))}
      </Popover>
    </>
  );
}
