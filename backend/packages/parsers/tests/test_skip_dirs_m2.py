from __future__ import annotations

from pathlib import Path

from ci_parsers import list_source_files


def test_list_source_files_skips_next_and_node_modules(tmp_path: Path) -> None:
    page = tmp_path / "app" / "page.tsx"
    page.parent.mkdir(parents=True)
    page.write_text("export default function P() {}", encoding="utf-8")
    junk = tmp_path / ".next" / "cache" / "page.js"
    junk.parent.mkdir(parents=True)
    junk.write_text("cached", encoding="utf-8")
    nm = tmp_path / "node_modules" / "pkg" / "index.ts"
    nm.parent.mkdir(parents=True)
    nm.write_text("export {}", encoding="utf-8")
    files = list_source_files(tmp_path, (".ts", ".tsx", ".js"))
    rels = {f.relative_to(tmp_path).as_posix() for f in files}
    assert rels == {"app/page.tsx"}
