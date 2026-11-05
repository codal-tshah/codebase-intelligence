"""Django file/class role classification and the role -> layer mapping."""

from __future__ import annotations

ROLE_LAYER: dict[str, str] = {
    "manage": "config",
    "wsgi": "config",
    "asgi": "config",
    "settings": "config",
    "apps": "config",
    "urls": "api",
    "views": "api",
    "serializers": "api",
    "middleware": "middleware",
    "permissions": "middleware",
    "models": "data",
    "managers": "data",
    "migration": "data",
    "services": "service",
    "signals": "service",
    "tasks": "service",
    "command": "service",
    "utils": "service",
    "admin": "ui",
    "forms": "ui",
    "templatetags": "ui",
    "tests": "test",
}

ROLE_LABEL: dict[str, str] = {
    "manage": "Command-line entry point",
    "wsgi": "WSGI entry point",
    "asgi": "ASGI entry point",
    "settings": "Project settings",
    "apps": "App configuration",
    "urls": "URL routing",
    "views": "Request handlers",
    "serializers": "Serializers",
    "middleware": "Middleware",
    "permissions": "Permissions",
    "models": "ORM models",
    "managers": "Model managers",
    "migration": "Database migration",
    "services": "Business logic",
    "signals": "Signal handlers",
    "tasks": "Background tasks",
    "command": "Management command",
    "utils": "Utilities",
    "admin": "Admin configuration",
    "forms": "Forms",
    "templatetags": "Template tags",
    "tests": "Tests",
}

ROLE_DESCRIPTION: dict[str, str] = {
    "views": "handle HTTP requests and build responses",
    "models": "define database schema and relations",
    "urls": "map request paths to handlers",
    "serializers": "convert and validate API data",
    "signals": "react to model and framework events",
    "tasks": "run work outside the request cycle",
    "middleware": "wrap every request and response",
    "tests": "verify behaviour",
}

# Third-party SDK import roots -> (display name, kind)
EXTERNAL_SDKS: dict[str, tuple[str, str]] = {
    "stripe": ("Stripe", "payments"),
    "boto3": ("AWS SDK (boto3)", "cloud"),
    "botocore": ("AWS SDK (boto3)", "cloud"),
    "celery": ("Celery", "queue"),
    "redis": ("Redis", "cache"),
    "django_redis": ("Redis", "cache"),
    "requests": ("HTTP (requests)", "http"),
    "httpx": ("HTTP (httpx)", "http"),
    "sentry_sdk": ("Sentry", "monitoring"),
    "sendgrid": ("SendGrid", "email"),
    "twilio": ("Twilio", "sms"),
    "openai": ("OpenAI", "ai"),
    "anthropic": ("Anthropic", "ai"),
    "firebase_admin": ("Firebase", "cloud"),
    "google": ("Google Cloud", "cloud"),
    "kafka": ("Kafka", "queue"),
    "pika": ("RabbitMQ", "queue"),
    "elasticsearch": ("Elasticsearch", "search"),
    "psycopg2": ("PostgreSQL", "database"),
    "pymongo": ("MongoDB", "database"),
    "channels": ("Django Channels", "realtime"),
    "rest_framework": ("Django REST framework", "framework"),
    "django_filters": ("django-filter", "framework"),
    "corsheaders": ("django-cors-headers", "framework"),
}

HTTP_METHODS = ("get", "post", "put", "patch", "delete", "head", "options")
VIEWSET_ACTIONS = {
    "list": "GET",
    "retrieve": "GET",
    "create": "POST",
    "update": "PUT",
    "partial_update": "PATCH",
    "destroy": "DELETE",
}

WRITE_ORM_METHODS = {
    "create",
    "bulk_create",
    "bulk_update",
    "update",
    "delete",
    "get_or_create",
    "update_or_create",
    "save",
}

BASE_MODEL_NAMES = {"Model", "AbstractUser", "AbstractBaseUser", "PolymorphicModel", "TimeStampedModel"}


def classify_module(rel_path: str) -> str:
    """Role of a module from its path. `rel_path` uses forward slashes."""
    parts = rel_path.split("/")
    filename = parts[-1]
    stem = filename[:-3] if filename.endswith(".py") else filename
    dirs = parts[:-1]

    if "migrations" in dirs:
        return "migration" if stem != "__init__" else "apps"
    if "tests" in dirs or "test" in dirs or stem.startswith("test_") or stem.endswith("_test") or stem in ("tests", "conftest"):
        return "tests"
    if "management" in dirs and "commands" in dirs:
        return "command"
    if "templatetags" in dirs:
        return "templatetags"
    if "settings" in dirs or stem == "settings" or stem.startswith("settings_") or stem in ("local_settings", "base_settings"):
        return "settings"
    if stem == "manage":
        return "manage"
    if stem in ("wsgi", "asgi"):
        return stem
    if stem == "apps":
        return "apps"
    if stem == "urls" or stem.startswith("urls_") or "urls" in dirs:
        return "urls"
    if stem in ("views", "viewsets", "api", "endpoints", "handlers") or "views" in dirs or stem.endswith("_views"):
        return "views"
    if stem == "serializers" or "serializers" in dirs or stem.endswith("_serializers"):
        return "serializers"
    if stem in ("models", "model") or "models" in dirs:
        return "models"
    if stem in ("managers", "querysets"):
        return "managers"
    if stem.startswith("middleware") or stem.endswith("_middleware") or "middleware" in dirs:
        return "middleware"
    if stem in ("permissions", "authentication", "auth_backends", "backends"):
        return "permissions"
    if stem == "signals":
        return "signals"
    if stem in ("tasks", "celery", "jobs", "workers"):
        return "tasks"
    if stem in ("admin",):
        return "admin"
    if stem in ("forms",) or "forms" in dirs:
        return "forms"
    if stem in ("services", "service", "usecases", "logic") or "services" in dirs:
        return "services"
    if stem in ("utils", "helpers", "common", "mixins", "constants", "exceptions"):
        return "utils"
    return "services"


def class_role(base_names: list[str], default_role: str) -> str:
    """Refine a class's role from its base classes (e.g. a View defined in a utils module)."""
    last = [b.split(".")[-1] for b in base_names]
    if any(b.endswith("Serializer") for b in last):
        return "serializers"
    if any(b.endswith(("View", "ViewSet", "APIView")) for b in last):
        return "views"
    if any(b.endswith("Form") or b == "ModelAdmin" for b in last):
        return "admin" if "ModelAdmin" in last else "forms"
    if any(b.endswith("Middleware") or b == "MiddlewareMixin" for b in last):
        return "middleware"
    if any(b.endswith("Permission") or b == "BasePermission" for b in last):
        return "permissions"
    if any(b in ("TestCase", "SimpleTestCase", "TransactionTestCase", "APITestCase") for b in last):
        return "tests"
    return default_role


def layer_for_role(role: str) -> str:
    return ROLE_LAYER.get(role, "service")
