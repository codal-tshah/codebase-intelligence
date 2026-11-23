# layered_fastapi (synthetic fixture)

A tiny FastAPI service in the common layered layout (routers → services → repositories → models),
written for regression tests. It reproduces patterns found while validating against a large real
FastAPI codebase, without copying any of its code:

- `@router.get("")` routes (the router prefix itself)
- `Annotated[Service, Depends(...)]` dependency aliases used as handler parameter types
- services holding a repository on `self.repo`, repositories using `select(Model)`
- Python 3.14 (PEP 758) `except A, B:` clauses
- nested packages (`app/routers/v1`) and FastAPI folder roles (`schemas/`, `repositories/`, `dependencies/`)
- generated coverage output in `htmlcov/` that must never be indexed
- `app/cycles/` modules for import-cycle suggestion regression (`TYPE_CHECKING`, lazy, merged runtime)
