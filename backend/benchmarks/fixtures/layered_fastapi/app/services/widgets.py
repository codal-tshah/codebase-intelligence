from app.core.errors import to_int
from app.repositories.widgets import WidgetRepository


class WidgetService:
    def __init__(self, repo: WidgetRepository):
        self.repo = repo

    def list_widgets(self):
        return self.repo.list_active()

    def find(self, raw_id):
        widget_id = to_int(raw_id)
        return self.repo.get(widget_id) if widget_id is not None else None

    def create(self, name: str):
        return self.repo.add(name)
