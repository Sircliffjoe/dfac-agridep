from django.urls import path
from agridep.apps.alerts.api.views import (
    USSDWebhookView,
    InboundSMSWebhookView,
    DeliveryReportWebhookView,
    BroadcastSMSAPIView,
)

urlpatterns = [
    path('ussd/', USSDWebhookView.as_view(), name='alerts-ussd-webhook'),
    path('sms/inbound/', InboundSMSWebhookView.as_view(), name='alerts-sms-inbound'),
    path('sms/delivery-report/', DeliveryReportWebhookView.as_view(), name='alerts-sms-delivery-report'),
    path('broadcast/', BroadcastSMSAPIView.as_view(), name='alerts-broadcast'),
]
