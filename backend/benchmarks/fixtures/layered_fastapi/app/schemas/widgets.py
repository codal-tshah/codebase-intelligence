from pydantic import BaseModel


class WidgetIn(BaseModel):
    name: str


class WidgetOut(BaseModel):
    id: int
    name: str
