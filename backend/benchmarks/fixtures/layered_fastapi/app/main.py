from fastapi import FastAPI

from app.routers.v1 import widgets

app = FastAPI(title="Widgets")
app.include_router(widgets.router, prefix="/v1")
