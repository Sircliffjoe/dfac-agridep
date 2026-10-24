from rest_framework import viewsets
from rest_framework.permissions import IsAuthenticated
from agridep.apps.common.permissions import ScopedQuerySetMixin
from .models import ProductionCycle, ProductionLog, ProduceBatch, HarvestForecast
from .serializers import (
    ProductionCycleSerializer,
    ProductionLogSerializer,
    ProduceBatchSerializer,
    HarvestForecastSerializer
)

class ProductionCycleViewSet(ScopedQuerySetMixin, viewsets.ModelViewSet):
    queryset = ProductionCycle.objects.all().select_related('farm', 'enterprise_type')
    serializer_class = ProductionCycleSerializer
    permission_classes = [IsAuthenticated]

class ProductionLogViewSet(ScopedQuerySetMixin, viewsets.ModelViewSet):
    queryset = ProductionLog.objects.all().select_related('cycle')
    serializer_class = ProductionLogSerializer
    permission_classes = [IsAuthenticated]

class ProduceBatchViewSet(ScopedQuerySetMixin, viewsets.ModelViewSet):
    queryset = ProduceBatch.objects.all().select_related('farm', 'produce_type', 'cycle')
    serializer_class = ProduceBatchSerializer
    permission_classes = [IsAuthenticated]

class HarvestForecastViewSet(ScopedQuerySetMixin, viewsets.ReadOnlyModelViewSet):
    queryset = HarvestForecast.objects.all().select_related('cycle')
    serializer_class = HarvestForecastSerializer
    permission_classes = [IsAuthenticated]
