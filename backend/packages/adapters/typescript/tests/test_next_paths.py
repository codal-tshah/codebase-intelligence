from ci_adapters_typescript.next_paths import join_route_path, next_app_segments, next_pages_segments


def test_app_router_strips_groups_and_slots():
    parts = ["app", "(dashboard)", "@modal", "settings", "page.tsx"]
    segs = next_app_segments(parts, file_stem="page")
    assert segs == ["settings"]
    assert join_route_path(segs) == "/settings"


def test_pages_api_path():
    parts = ["pages", "api", "nested", "hello.ts"]
    segs = next_pages_segments(parts, file_stem="hello", is_api=True)
    assert join_route_path(segs or []) == "/api/nested/hello"
