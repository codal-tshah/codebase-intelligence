from django.test import TestCase

from . import services
from .models import Item


class CheckoutTests(TestCase):
    def test_checkout_marks_paid(self):
        item = Item.objects.create(title="x", category_id=1)
        order = services.checkout(item.pk, buyer=None)
        self.assertTrue(order.paid)
