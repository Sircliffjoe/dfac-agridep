from rest_framework import generics, permissions, status
from rest_framework.views import APIView
from rest_framework.response import Response
from django.shortcuts import get_object_or_404
from agridep.apps.inputs.models import (
    InputSupplier,
    InputCatalogItem,
    InputOrder,
    DeliveryConfirmationChannel,
)
from agridep.apps.inputs.api.serializers import (
    InputSupplierSerializer,
    InputCatalogItemSerializer,
    InputOrderSerializer,
)
from agridep.apps.inputs.services import (
    create_input_order,
    dispatch_input_order,
    confirm_input_delivery,
    verify_tranche_input_delivery_gate,
)
from agridep.apps.finance.models import LoanTranche


class SupplierListCreateAPIView(generics.ListCreateAPIView):
    """Lists verified suppliers or registers a new input supplier."""
    queryset = InputSupplier.objects.filter(is_verified=True)
    serializer_class = InputSupplierSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        qs = super().get_queryset()
        category = self.request.query_params.get('category')
        if category:
            qs = qs.filter(category=category)
        return qs


class CatalogItemListCreateAPIView(generics.ListCreateAPIView):
    """Lists available input catalog items with pricing and specifications."""
    queryset = InputCatalogItem.objects.filter(in_stock=True)
    serializer_class = InputCatalogItemSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        qs = super().get_queryset()
        supplier_id = self.request.query_params.get('supplier_id')
        enterprise_id = self.request.query_params.get('enterprise_id')
        if supplier_id:
            qs = qs.filter(supplier_id=supplier_id)
        if enterprise_id:
            qs = qs.filter(enterprise_type_id=enterprise_id)
        return qs


class InputOrderListCreateAPIView(generics.ListCreateAPIView):
    """Lists input orders or places a new order."""
    queryset = InputOrder.objects.all().select_related('farmer', 'supplier', 'tranche').prefetch_related('items__catalog_item')
    serializer_class = InputOrderSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        user = self.request.user
        qs = super().get_queryset()
        if user.is_staff or getattr(user, 'role', '') in ['ADMIN', 'DFAC_COORDINATOR', 'LENDER']:
            return qs
        if hasattr(user, 'supplier_profile'):
            return qs.filter(supplier=user.supplier_profile)
        if hasattr(user, 'farmer_profile'):
            return qs.filter(farmer=user.farmer_profile)
        return qs.none()


class InputOrderDeliveryConfirmAPIView(APIView):
    """
    Confirms delivery of an input order on farm, unblocking subsequent loan tranches.
    """
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, pk):
        order = get_object_or_404(InputOrder, pk=pk)
        channel = request.data.get('channel', DeliveryConfirmationChannel.FIELD_OFFICER_INSPECTION)
        notes = request.data.get('notes', '')

        try:
            confirmed_order = confirm_input_delivery(
                order=order,
                confirmation_channel=channel,
                confirmed_by=request.user,
                notes=notes
            )
            serializer = InputOrderSerializer(confirmed_order)
            return Response(serializer.data, status=status.HTTP_200_OK)
        except Exception as e:
            return Response({"detail": str(e)}, status=status.HTTP_400_BAD_REQUEST)


class TrancheDeliveryGateCheckAPIView(APIView):
    """Verifies whether a loan tranche can be disbursed based on input delivery status."""
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request, tranche_id):
        tranche = get_object_or_404(LoanTranche, pk=tranche_id)
        result = verify_tranche_input_delivery_gate(tranche)
        return Response(result, status=status.HTTP_200_OK)
