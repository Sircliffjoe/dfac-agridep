from django.http import HttpResponse
from django.views.decorators.csrf import csrf_exempt
from django.utils.decorators import method_decorator
from rest_framework import viewsets, permissions, status
from rest_framework.views import APIView
from rest_framework.response import Response
from drf_spectacular.utils import extend_schema, OpenApiResponse
from agridep.apps.alerts.models import AlertNotification, AlertRule, USSDSession
from agridep.apps.alerts.ussd import USSDHandler
from agridep.apps.alerts.services import send_transactional_sms


@method_decorator(csrf_exempt, name='dispatch')
class USSDWebhookView(APIView):
    """
    Africa's Talking USSD Gateway Webhook.
    Receives HTTP POST requests when a farmer dials *384*223# or responds to a prompt.
    Returns plain text responses prefixed with 'CON ' or 'END '.
    """
    authentication_classes = []
    permission_classes = [permissions.AllowAny]

    def post(self, request):
        session_id = request.data.get('sessionId') or request.POST.get('sessionId', '')
        phone_number = request.data.get('phoneNumber') or request.POST.get('phoneNumber', '')
        text = request.data.get('text') or request.POST.get('text', '')
        network_code = request.data.get('networkCode') or request.POST.get('networkCode', 'MTN_NG')

        if not session_id or not phone_number:
            return HttpResponse("END Invalid request payload.", content_type='text/plain')

        handler = USSDHandler(
            session_id=session_id,
            phone_number=phone_number,
            text=text,
            network_code=network_code
        )
        response_text = handler.handle()
        return HttpResponse(response_text, content_type='text/plain')


class InboundSMSWebhookView(APIView):
    """Africa's Talking incoming two-way SMS webhook."""
    authentication_classes = []
    permission_classes = [permissions.AllowAny]

    def post(self, request):
        from_phone = request.data.get('from', '')
        text = request.data.get('text', '')
        # Log incoming SMS
        return Response({"status": "received"}, status=status.HTTP_200_OK)


class DeliveryReportWebhookView(APIView):
    """Africa's Talking delivery report callback."""
    authentication_classes = []
    permission_classes = [permissions.AllowAny]

    def post(self, request):
        message_id = request.data.get('id', '')
        status_val = request.data.get('status', '')

        if message_id:
            notif = AlertNotification.objects.filter(provider_reference=message_id).first()
            if notif:
                st = status_val.lower()
                if any(x in st for x in ['success', 'deliver', 'sent']):
                    notif.status = 'DELIVERED'
                else:
                    notif.status = 'FAILED'
                notif.save(update_fields=['status', 'updated_at'])

        return Response({"status": "ack"}, status=status.HTTP_200_OK)


class BroadcastSMSAPIView(APIView):
    """Admin endpoint to broadcast advisory or emergency SMS to farmers by LGA."""
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        if not (request.user.is_superuser or request.user.role == 'DFAC_ADMIN'):
            return Response({"error": "Admin access required"}, status=status.HTTP_403_FORBIDDEN)

        lga = request.data.get('lga')
        message = request.data.get('message')
        if not message:
            return Response({"error": "Message is required"}, status=status.HTTP_400_BAD_REQUEST)

        from agridep.apps.registry.models import Farmer
        qs = Farmer.objects.filter(phone_normalized__isnull=False).exclude(phone_normalized='')
        if lga:
            qs = qs.filter(lga=lga)

        dispatched = 0
        for farmer in qs[:50]:
            send_transactional_sms(farmer.phone_normalized, message, priority='HIGH', user=farmer.user)
            dispatched += 1

        return Response({"message": f"Broadcast sent to {dispatched} farmers", "count": dispatched})
