from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException

from app.dependencies.services import get_widget_service
from app.schemas.widgets import WidgetIn, WidgetOut
from app.services.widgets import WidgetService

router = APIRouter(prefix="/widgets", tags=["widgets"])

WidgetServiceDep = Annotated[WidgetService, Depends(get_widget_service)]


@router.get("", response_model=list[WidgetOut])
def list_widgets(service: WidgetServiceDep):
    return service.list_widgets()


@router.post(
    "",
    response_model=WidgetOut,
    status_code=201,
)
def create_widget(payload: WidgetIn, service: WidgetServiceDep):
    return service.create(payload.name)


@router.get("/{widget_id}", response_model=WidgetOut)
def get_widget(widget_id: str, service: WidgetServiceDep):
    widget = service.find(widget_id)
    if widget is None:
        raise HTTPException(status_code=404)
    return widget
