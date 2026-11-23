from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.widget import Widget


class WidgetRepository:
    def __init__(self, session: Session):
        self.session = session

    def list_active(self) -> list[Widget]:
        return list(self.session.execute(select(Widget)).scalars())

    def get(self, widget_id: int) -> Widget | None:
        return self.session.get(Widget, widget_id)

    def add(self, name: str) -> Widget:
        widget = Widget(name=name)
        self.session.add(widget)
        return widget
