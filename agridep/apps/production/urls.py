from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import (
    ProductionCycleViewSet,
    ProductionLogViewSet,
    ProduceBatchViewSet,
    HarvestForecastViewSet
)

router = DefaultRouter()
router.register('cycles', ProductionCycleViewSet, basename='cycle')
router.register('logs', ProductionLogViewSet, basename='log')
router.register('batches', ProduceBatchViewSet, basename='batch')
router.register('forecasts', HarvestForecastViewSet, basename='forecast')

urlpatterns = [
    path('', include(router.urls)),
]
