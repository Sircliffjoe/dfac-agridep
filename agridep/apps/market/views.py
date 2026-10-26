from rest_framework import viewsets, status
from rest_framework.views import APIView
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated

from agridep.apps.common.permissions import ScopedQuerySetMixin
from agridep.apps.registry.models import EnterpriseType
from agridep.apps.market.models import (
    BuyerDemand,
    ProduceMatch,
    OfftakeTransaction,
    CommodityPrice,
)
from agridep.apps.market.serializers import (
    BuyerDemandSerializer,
    ProduceMatchSerializer,
    OfftakeTransactionSerializer,
    CommodityPriceSerializer,
)
from agridep.apps.market.services import (
    find_matching_produce_for_demand,
    propose_buyer_matches_for_demand,
    confirm_produce_match,
    calculate_regional_price_index,
    analyze_supply_demand_gap,
)


class CommodityPriceViewSet(ScopedQuerySetMixin, viewsets.ModelViewSet):
    queryset = CommodityPrice.objects.all().select_related('enterprise_type')
    serializer_class = CommodityPriceSerializer
    permission_classes = [IsAuthenticated]


class BuyerDemandViewSet(ScopedQuerySetMixin, viewsets.ModelViewSet):
    queryset = BuyerDemand.objects.all().select_related('buyer', 'enterprise_type').prefetch_related('matches')
    serializer_class = BuyerDemandSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        user = self.request.user
        qs = super().get_queryset()
        role = getattr(user, 'role', '')
        if role == 'BUYER':
            return qs.filter(buyer__user=user)
        return qs

    def perform_create(self, serializer):
        user = self.request.user
        buyer = getattr(user, 'buyer_profile', None)
        if not serializer.validated_data.get('buyer') and buyer:
            serializer.save(buyer=buyer)
        else:
            serializer.save()

    @action(detail=True, methods=['get'])
    def candidate_matches(self, request, pk=None):
        """Finds candidate smallholder batches matching radius and harvest window."""
        demand = self.get_object()
        candidates = find_matching_produce_for_demand(demand)
        summary = []
        for c in candidates:
            batch = c['batch']
            summary.append({
                'batch_id': str(batch.id),
                'batch_code': batch.reference_code,
                'available_volume_kg': float(c['available_volume_kg']),
                'distance_km': float(c['distance_km']),
                'window_start': c['window_start'],
                'window_end': c['window_end'],
                'grade': c['grade'],
                'location': f"{c['farm_lga']}, {c['farm_state']}",
            })
        return Response({
            'demand_code': demand.reference_code,
            'target_volume_kg': float(demand.target_volume_kg),
            'remaining_unmatched_kg': float(demand.remaining_unmatched_volume_kg),
            'candidates_count': len(summary),
            'candidates': summary
        })

    @action(detail=True, methods=['post'])
    def auto_match(self, request, pk=None):
        """Runs RULE-04 algorithm to automatically allocate batches up to target volume."""
        demand = self.get_object()
        created_matches = propose_buyer_matches_for_demand(demand)
        serializer = ProduceMatchSerializer(created_matches, many=True, context={'request': request})
        return Response({
            'demand_code': demand.reference_code,
            'matches_created_count': len(created_matches),
            'fulfilled_volume_kg': float(demand.fulfilled_volume_kg),
            'status': demand.status,
            'matches': serializer.data
        }, status=status.HTTP_200_OK)


class ProduceMatchViewSet(ScopedQuerySetMixin, viewsets.ModelViewSet):
    queryset = ProduceMatch.objects.all().select_related('buyer_demand', 'produce_batch', 'buyer_demand__buyer', 'produce_batch__farm__farmer')
    serializer_class = ProduceMatchSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        user = self.request.user
        qs = super().get_queryset()
        role = getattr(user, 'role', '')
        if role == 'BUYER':
            return qs.filter(buyer_demand__buyer__user=user)
        elif role == 'FARMER':
            return qs.filter(produce_batch__farm__farmer__user=user)
        return qs

    @action(detail=True, methods=['post'])
    def confirm(self, request, pk=None):
        """Confirms match into binding contract, creates OfftakeTransaction and unmasks contact info."""
        match = self.get_object()
        offtake = confirm_produce_match(match, confirmed_by=request.user)
        serializer = OfftakeTransactionSerializer(offtake, context={'request': request})
        return Response({
            'message': 'Contract confirmed. Off-take transaction waybill generated.',
            'offtake_transaction': serializer.data
        }, status=status.HTTP_200_OK)


class OfftakeTransactionViewSet(ScopedQuerySetMixin, viewsets.ModelViewSet):
    queryset = OfftakeTransaction.objects.all().select_related('match', 'match__buyer_demand__buyer', 'match__produce_batch__farm__farmer')
    serializer_class = OfftakeTransactionSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        user = self.request.user
        qs = super().get_queryset()
        role = getattr(user, 'role', '')
        if role == 'BUYER':
            return qs.filter(match__buyer_demand__buyer__user=user)
        elif role == 'FARMER':
            return qs.filter(match__produce_batch__farm__farmer__user=user)
        return qs


class MarketIntelligenceAPIView(APIView):
    """
    Exposes regional commodity price index and supply-demand gap intelligence.
    """
    permission_classes = [IsAuthenticated]

    def get(self, request):
        enterprise_id = request.query_params.get('enterprise_id')
        state = request.query_params.get('state', 'Delta')
        days = int(request.query_params.get('days', 30))
        window_days = int(request.query_params.get('window_days', 60))

        enterprise = None
        if enterprise_id:
            enterprise = EnterpriseType.objects.filter(pk=enterprise_id).first()

        price_index = calculate_regional_price_index(enterprise_type=enterprise, state=state, days=days)
        gap_analysis = analyze_supply_demand_gap(enterprise_type=enterprise, state=state, window_days=window_days)

        return Response({
            'state': state,
            'price_index': price_index,
            'supply_demand_gap': gap_analysis
        }, status=status.HTTP_200_OK)

