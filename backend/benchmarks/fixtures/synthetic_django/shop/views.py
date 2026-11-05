from django.http import JsonResponse
from django.views import View
from django.views.decorators.http import require_http_methods

from . import services
from .models import Item


def list_items(request):
    items = Item.objects.select_related("category").all()[:50]
    return JsonResponse({"items": [i.title for i in items]})


def get_item(request, pk: int):
    item = Item.objects.get(pk=pk)
    return JsonResponse({"title": item.title, "category": item.category.name})


@require_http_methods(["POST"])
def create_order(request, pk: int):
    order = services.checkout(pk, request.user)
    return JsonResponse({"order": order.pk, "paid": order.paid})


class ItemDetailView(View):
    model = Item

    def get(self, request, pk: int):
        return get_item(request, pk)
