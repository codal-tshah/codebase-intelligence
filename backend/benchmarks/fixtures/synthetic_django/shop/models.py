from django.conf import settings
from django.db import models


class TimeStamped(models.Model):
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        abstract = True


class Category(models.Model):
    name = models.CharField(max_length=100)


class Item(TimeStamped):
    title = models.CharField(max_length=200)
    category = models.ForeignKey(Category, on_delete=models.CASCADE)

    def __str__(self) -> str:
        return self.title


class Order(models.Model):
    """A purchase of one item by a user."""

    item = models.ForeignKey("shop.Item", on_delete=models.PROTECT, related_name="orders")
    buyer = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    quantity = models.PositiveIntegerField(default=1)
    paid = models.BooleanField(default=False)
