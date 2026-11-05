"""Role classification and lookup tables for the TypeScript/JavaScript analyzer."""

from __future__ import annotations

import re

ROLE_LAYER: dict[str, str] = {
    "components": "ui",
    "pages": "ui",
    "hooks": "ui",
    "styles": "ui",
    "stores": "service",
    "api-client": "service",
    "services": "service",
    "utils": "service",
    "types": "service",
    "urls": "api",
    "views": "api",
    "middleware": "middleware",
    "permissions": "middleware",
    "models": "data",
    "settings": "config",
    "entry": "config",
    "tests": "test",
}

ROLE_LABEL: dict[str, str] = {
    "components": "UI components",
    "pages": "Pages",
    "hooks": "React hooks",
    "styles": "Styles",
    "stores": "State management",
    "api-client": "API client",
    "services": "Business logic",
    "utils": "Utilities",
    "types": "Type definitions",
    "urls": "HTTP routes",
    "views": "Controllers",
    "middleware": "Middleware",
    "permissions": "Auth guards",
    "models": "Data models",
    "settings": "Configuration",
    "entry": "Entry point",
    "tests": "Tests",
}

# npm package (or scope) -> (display name, kind). Plain libraries (react, lodash) are not services.
JS_SDKS: dict[str, tuple[str, str]] = {
    "stripe": ("Stripe", "payments"),
    "@stripe": ("Stripe", "payments"),
    "@aws-sdk": ("AWS SDK", "cloud"),
    "aws-sdk": ("AWS SDK", "cloud"),
    "firebase": ("Firebase", "cloud"),
    "firebase-admin": ("Firebase", "cloud"),
    "@supabase": ("Supabase", "database"),
    "openai": ("OpenAI", "ai"),
    "@anthropic-ai": ("Anthropic", "ai"),
    "@sentry": ("Sentry", "monitoring"),
    "twilio": ("Twilio", "sms"),
    "@sendgrid": ("SendGrid", "email"),
    "nodemailer": ("SMTP (nodemailer)", "email"),
    "redis": ("Redis", "cache"),
    "ioredis": ("Redis", "cache"),
    "mongoose": ("MongoDB", "database"),
    "mongodb": ("MongoDB", "database"),
    "pg": ("PostgreSQL", "database"),
    "mysql2": ("MySQL", "database"),
    "mysql": ("MySQL", "database"),
    "@prisma": ("Prisma", "database"),
    "sequelize": ("Sequelize", "database"),
    "typeorm": ("TypeORM", "database"),
    "drizzle-orm": ("Drizzle ORM", "database"),
    "kafkajs": ("Kafka", "queue"),
    "amqplib": ("RabbitMQ", "queue"),
    "bullmq": ("BullMQ", "queue"),
    "socket.io": ("Socket.IO", "realtime"),
    "socket.io-client": ("Socket.IO", "realtime"),
    "@google-cloud": ("Google Cloud", "cloud"),
    "googleapis": ("Google APIs", "cloud"),
    "@auth0": ("Auth0", "auth"),
    "next-auth": ("NextAuth", "auth"),
    "@clerk": ("Clerk", "auth"),
    "passport": ("Passport", "auth"),
    "@elastic": ("Elasticsearch", "search"),
    "algoliasearch": ("Algolia", "search"),
    "@apollo": ("Apollo GraphQL", "graphql"),
    "graphql-request": ("GraphQL", "graphql"),
    "@tanstack": ("TanStack Query", "framework"),
}

FRAMEWORK_PACKAGES: dict[str, str] = {
    "react": "react",
    "react-dom": "react",
    "next": "nextjs",
    "vue": "vue",
    "express": "express",
    "@nestjs": "nestjs",
    "fastify": "fastify",
    "koa": "koa",
    "react-router": "react-router",
    "react-router-dom": "react-router",
}

HTTP_VERBS = ("get", "post", "put", "patch", "delete", "head", "options")
ROUTE_VERBS = (*HTTP_VERBS, "all")
ROUTER_OBJECTS = re.compile(r"^(app|server|router|api|routes?|\w*Router|\w*router)$")
HTTP_CLIENT_OBJECTS = re.compile(r"(axios|http|api|client|ky|got|superagent|request|\$http)$", re.I)
HTTP_WRAPPER_FUNCS = re.compile(r"^(fetch|request|(get|post|put|patch|delete)(json|data|api|request)?|(fetch|send)\w*)$", re.I)
NEST_ROUTE_DECORATORS = {"Get": "GET", "Post": "POST", "Put": "PUT", "Patch": "PATCH", "Delete": "DELETE", "All": "ALL", "Head": "HEAD", "Options": "OPTIONS"}

_PASCAL = re.compile(r"^[A-Z][A-Za-z0-9]*$")
_HOOK = re.compile(r"^use[A-Z0-9]")


def is_component_name(name: str) -> bool:
    return bool(_PASCAL.match(name))


def is_hook_name(name: str) -> bool:
    return bool(_HOOK.match(name))


def package_root(spec: str) -> str:
    """`@scope/pkg/sub` -> `@scope/pkg`; `pkg/sub` -> `pkg`."""
    parts = spec.split("/")
    if spec.startswith("@") and len(parts) > 1:
        return "/".join(parts[:2])
    return parts[0]


def sdk_for(spec: str) -> tuple[str, str] | None:
    root = package_root(spec)
    if root in JS_SDKS:
        return JS_SDKS[root]
    scope = root.split("/")[0]
    return JS_SDKS.get(scope) if scope.startswith("@") else None


def framework_for(spec: str) -> str | None:
    root = package_root(spec)
    return FRAMEWORK_PACKAGES.get(root) or FRAMEWORK_PACKAGES.get(root.split("/")[0])


def classify_module(rel: str) -> str:
    """Role of a module from its path (forward slashes)."""
    parts = rel.lower().split("/")
    name = parts[-1]
    stem = name.split(".")[0]
    dirs = parts[:-1]
    if ".test." in name or ".spec." in name or "__tests__" in dirs or "tests" in dirs or "test" in dirs or "e2e" in dirs:
        return "tests"
    if ".config." in name or stem in ("config", "env", "constants") or name.startswith(("vite.", "webpack.", "next.config", "tailwind", "postcss", "jest.", "eslint")):
        return "settings"
    if stem in ("main", "index", "server", "app") and len(dirs) <= 2 and not any(d in ("components", "pages") for d in dirs):
        return "entry"
    if "pages" in dirs and "api" in dirs:
        return "urls"
    if "app" in dirs and stem == "route":
        return "urls"
    if "pages" in dirs or "views" in dirs or "screens" in dirs or stem in ("page", "layout"):
        return "pages"
    if "components" in dirs or "ui" in dirs or "widgets" in dirs:
        return "components"
    if "hooks" in dirs or stem.startswith("use"):
        return "hooks"
    if any(d in dirs for d in ("store", "stores", "state", "redux", "slices", "context", "contexts")) or stem.endswith(("slice", "store", "context")):
        return "stores"
    if "routes" in dirs or "routers" in dirs or stem.endswith(("routes", "router")) or stem == "routes":
        return "urls"
    if "controllers" in dirs or stem.endswith("controller"):
        return "views"
    if "middleware" in dirs or "middlewares" in dirs or stem.endswith("middleware"):
        return "middleware"
    if "guards" in dirs or stem.endswith(("guard", "auth")):
        return "permissions"
    if any(d in dirs for d in ("models", "entities", "schemas", "prisma")) or stem.endswith(("model", "entity", "schema")):
        return "models"
    if "api" in dirs or stem in ("api", "client", "http", "fetcher") or stem.endswith(("api", "client")):
        return "api-client"
    if "services" in dirs or stem.endswith("service"):
        return "services"
    if "types" in dirs or stem in ("types", "interfaces") or name.endswith(".types.ts"):
        return "types"
    if "styles" in dirs or stem in ("theme", "styles") or stem.endswith("theme"):
        return "styles"
    if any(d in dirs for d in ("utils", "lib", "helpers", "common", "shared")):
        return "utils"
    return "utils"


def layer_for_role(role: str) -> str:
    return ROLE_LAYER.get(role, "service")
