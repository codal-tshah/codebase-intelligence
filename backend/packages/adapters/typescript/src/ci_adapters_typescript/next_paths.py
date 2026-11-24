"""Next.js App Router and Pages Router public URL paths from file paths."""

from __future__ import annotations


def _is_route_group(segment: str) -> bool:
    return segment.startswith("(") and segment.endswith(")")


def _is_parallel_slot(segment: str) -> bool:
    return segment.startswith("@") and not segment.startswith("@/")  # not alias


def _canonical_segment(segment: str) -> str | None:
    if _is_route_group(segment) or _is_parallel_slot(segment):
        return None
    return segment


def next_app_segments(parts: list[str], *, file_stem: str) -> list[str] | None:
    """Segments under ``app/`` for ``page.tsx``, ``route.ts``, or ``layout.tsx``."""
    if "app" not in parts:
        return None
    idx = len(parts) - 1 - parts[::-1].index("app")
    raw = parts[idx + 1 : -1]
    segs: list[str] = []
    for p in raw:
        c = _canonical_segment(p)
        if c is not None:
            segs.append(c)
    if file_stem not in ("page", "route", "layout"):
        return None
    return segs


def next_pages_segments(parts: list[str], *, file_stem: str, is_api: bool) -> list[str] | None:
    if "pages" not in parts:
        return None
    idx = parts.index("pages")
    if is_api:
        tail = parts[idx + 1 : -1]
        if not tail or tail[0] != "api":
            return None
        segs = ["api", *_canonical_parts(tail[1:]), file_stem]
    else:
        segs = [*_canonical_parts(parts[idx + 1 : -1]), file_stem]
    if segs and segs[-1] == "index":
        segs = segs[:-1]
    return segs


def _canonical_parts(segments: list[str]) -> list[str]:
    out: list[str] = []
    for p in segments:
        c = _canonical_segment(p)
        if c is not None:
            out.append(c)
    return out


def join_route_path(segments: list[str]) -> str:
    if not segments:
        return "/"
    return "/" + "/".join(segments)


def is_next_middleware_path(rel: str) -> bool:
    norm = rel.replace("\\", "/")
    return norm in {
        "middleware.ts",
        "middleware.js",
        "src/middleware.ts",
        "src/middleware.js",
    }
