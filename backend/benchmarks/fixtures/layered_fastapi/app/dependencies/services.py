from typing import Annotated

from fastapi import Depends
from sqlalchemy.orm import Session

from app.db.session import get_session
from app.repositories.widgets import WidgetRepository
from app.services.widgets import WidgetService


def get_widget_service(session: Annotated[Session, Depends(get_session)]) -> WidgetService:
    return WidgetService(WidgetRepository(session))
