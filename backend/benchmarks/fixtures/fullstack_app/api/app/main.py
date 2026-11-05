"""FastAPI application entry point."""
from fastapi import FastAPI

from app.routers import items, orders

app = FastAPI(title="Shop")
app.include_router(items.router, prefix="/api")
app.include_router(orders.router, prefix="/api")


@app.get("/health")
def health():
    return {"ok": True}
