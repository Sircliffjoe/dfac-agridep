from django.urls import path
from agridep.apps.inputs.api.views import (
    SupplierListCreateAPIView,
    CatalogItemListCreateAPIView,
    InputOrderListCreateAPIView,
    InputOrderDeliveryConfirmAPIView,
    TrancheDeliveryGateCheckAPIView,
)

urlpatterns = [
    path('suppliers/', SupplierListCreateAPIView.as_view(), name='inputs-suppliers-list'),
    path('catalog/', CatalogItemListCreateAPIView.as_view(), name='inputs-catalog-list'),
    path('orders/', InputOrderListCreateAPIView.as_view(), name='inputs-orders-list'),
    path('orders/<uuid:pk>/confirm-delivery/', InputOrderDeliveryConfirmAPIView.as_view(), name='inputs-order-confirm-delivery'),
    path('tranche-gate/<uuid:tranche_id>/', TrancheDeliveryGateCheckAPIView.as_view(), name='inputs-tranche-gate-check'),
]
