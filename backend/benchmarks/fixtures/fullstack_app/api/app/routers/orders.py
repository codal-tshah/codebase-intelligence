import stripe
from fastapi import APIRouter, Depends

from app.db import Order, get_db

router = APIRouter(prefix="/orders")


@router.post("/")
def checkout(item_id: int, db=Depends(get_db)):
    order = Order(item_id=item_id)
    db.add(order)
    stripe.PaymentIntent.create(amount=100)
    return order
