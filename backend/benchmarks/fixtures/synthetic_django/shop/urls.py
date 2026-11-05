from django.urls import path

from . import views

urlpatterns = [
    path("categories/", views.list_items),
    path("items/<int:pk>/order/", views.create_order),
    path("items/<int:pk>/detail/", views.ItemDetailView.as_view()),
]
