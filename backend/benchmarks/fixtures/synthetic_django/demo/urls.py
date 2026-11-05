from django.urls import include, path

from shop import views

urlpatterns = [
    path("api/items/", views.list_items),
    path("api/items/<int:pk>/", views.get_item),
    path("shop/", include("shop.urls")),
]
