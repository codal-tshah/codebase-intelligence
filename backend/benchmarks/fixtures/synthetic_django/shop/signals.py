from django.db.models.signals import post_save
from django.dispatch import receiver

from .models import Item


@receiver(post_save, sender=Item)
def invalidate_item_cache(sender, instance, **kwargs):
    print("item changed", instance.pk)
