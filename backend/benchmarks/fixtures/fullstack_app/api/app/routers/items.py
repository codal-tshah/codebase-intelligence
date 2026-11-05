from fastapi import APIRouter, Depends
from sqlalchemy import select

from app.auth import get_current_user
from app.db import Item, get_db

router = APIRouter(prefix="/items", tags=["items"])


@router.get("/")
def list_items(db=Depends(get_db)):
    return db.scalars(select(Item)).all()


@router.get("/{item_id}")
def get_item(item_id: int, db=Depends(get_db)):
    return db.get(Item, item_id)


@router.post("/")
def create_item(name: str, db=Depends(get_db), user=Depends(get_current_user)):
    item = Item(name=name)
    db.add(item)
    db.commit()
    return item
