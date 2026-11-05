"""Order business logic."""

import stripe

from .models import Item, Order


def charge(order: Order) -> bool:
    stripe.Charge.create(amount=order.quantity * 100, currency="usd")
    return True


def checkout(item_id: int, buyer, quantity: int = 1) -> Order:
    item = Item.objects.get(pk=item_id)
    order = Order.objects.create(item=item, buyer=buyer, quantity=quantity)
    if charge(order):
        order.paid = True
        order.save()
    return order
