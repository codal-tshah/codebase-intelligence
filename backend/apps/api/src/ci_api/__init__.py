__version__ = "0.4.0"

from ci_api.main import app, create_app  # noqa: E402 - version must exist before main imports it

__all__ = ["__version__", "app", "create_app"]
