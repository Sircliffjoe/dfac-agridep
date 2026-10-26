import json
import logging
import urllib.request
import urllib.parse
from abc import ABC, abstractmethod
from typing import Dict, Any, List
from django.conf import settings
from agridep.apps.common.models import SystemParameter

logger = logging.getLogger(__name__)


class SMSAdapter(ABC):
    """Abstract interface for telecom SMS dispatch providers."""

    @abstractmethod
    def send_sms(self, to_phone: str, message: str, sender_id: str = None) -> Dict[str, Any]:
        pass

    @abstractmethod
    def send_bulk_sms(self, recipients: List[str], message: str) -> Dict[str, Any]:
        pass


class MockSMSAdapter(SMSAdapter):
    """In-memory mock adapter for local development, CI pipelines, and unit tests."""

    def __init__(self):
        self.outbox = []

    def send_sms(self, to_phone: str, message: str, sender_id: str = None) -> Dict[str, Any]:
        msg_record = {
            "to": to_phone,
            "message": message,
            "sender_id": sender_id or "DFAC",
            "status": "Success",
            "messageId": f"AT_MOCK_{len(self.outbox) + 1:06d}",
            "cost": "NGN 4.00"
        }
        self.outbox.append(msg_record)
        logger.info(f"[MockSMS] Dispatched to {to_phone}: {message[:60]}...")
        return {
            "status": "SUCCESS",
            "provider": "MOCK",
            "data": {
                "SMSMessageData": {
                    "Message": "Sent to 1/1 Total Recipients",
                    "Recipients": [msg_record]
                }
            }
        }

    def send_bulk_sms(self, recipients: List[str], message: str) -> Dict[str, Any]:
        dispatched = []
        for phone in recipients:
            res = self.send_sms(phone, message)
            dispatched.append(res['data']['SMSMessageData']['Recipients'][0])
        return {
            "status": "SUCCESS",
            "provider": "MOCK",
            "data": {
                "SMSMessageData": {
                    "Message": f"Sent to {len(recipients)}/{len(recipients)} Total Recipients",
                    "Recipients": dispatched
                }
            }
        }


class AfricasTalkingSMSAdapter(SMSAdapter):
    """
    Live telecom adapter for Africa's Talking SMS API.
    Used in production across Nigerian mobile networks (MTN, Airtel, Glo, 9mobile).
    """

    def __init__(self):
        self.username = getattr(settings, 'AFRICAS_TALKING_USERNAME', 'sandbox')
        self.api_key = getattr(settings, 'AFRICAS_TALKING_API_KEY', '')
        self.sender_id = getattr(settings, 'AFRICAS_TALKING_SENDER_ID', 'DFAC')
        self.api_url = 'https://api.africastalking.com/version1/messaging'

        if self.username == 'sandbox':
            self.api_url = 'https://api.sandbox.africastalking.com/version1/messaging'

    def send_sms(self, to_phone: str, message: str, sender_id: str = None) -> Dict[str, Any]:
        # Fallback to Mock if API Key is not configured
        if not self.api_key or self.api_key in ['mock_key', 'dev_key']:
            return MockSMSAdapter().send_sms(to_phone, message, sender_id)

        headers = {
            'apiKey': self.api_key,
            'Content-Type': 'application/x-www-form-urlencoded',
            'Accept': 'application/json'
        }
        data = {
            'username': self.username,
            'to': to_phone,
            'message': message,
        }
        active_sender = sender_id or self.sender_id
        if active_sender:
            data['from'] = active_sender

        encoded_data = urllib.parse.urlencode(data).encode('utf-8')
        req = urllib.request.Request(self.api_url, data=encoded_data, headers=headers, method='POST')

        try:
            with urllib.request.urlopen(req, timeout=12) as response:
                resp_text = response.read().decode('utf-8')
                return {
                    "status": "SUCCESS",
                    "provider": "AFRICAS_TALKING",
                    "data": json.loads(resp_text) if resp_text else {}
                }
        except Exception as e:
            logger.exception(f"Africa's Talking connection exception: {e}")
            return {
                "status": "FAILED",
                "provider": "AFRICAS_TALKING",
                "error": str(e)
            }

    def send_bulk_sms(self, recipients: List[str], message: str) -> Dict[str, Any]:
        if not self.api_key or self.api_key in ['mock_key', 'dev_key']:
            return MockSMSAdapter().send_bulk_sms(recipients, message)

        to_string = ",".join(recipients)
        headers = {
            'apiKey': self.api_key,
            'Content-Type': 'application/x-www-form-urlencoded',
            'Accept': 'application/json'
        }
        data = {
            'username': self.username,
            'to': to_string,
            'message': message,
        }
        if self.sender_id:
            data['from'] = self.sender_id

        encoded_data = urllib.parse.urlencode(data).encode('utf-8')
        req = urllib.request.Request(self.api_url, data=encoded_data, headers=headers, method='POST')

        try:
            with urllib.request.urlopen(req, timeout=20) as response:
                resp_text = response.read().decode('utf-8')
                return {
                    "status": "SUCCESS",
                    "provider": "AFRICAS_TALKING",
                    "data": json.loads(resp_text) if resp_text else {}
                }
        except Exception as e:
            return {"status": "FAILED", "provider": "AFRICAS_TALKING", "error": str(e)}


def get_sms_adapter() -> SMSAdapter:
    """
    Factory function returning the active SMSAdapter.
    Controlled dynamically by SystemParameter 'alerts_sms_provider'.
    """
    provider_name = SystemParameter.get('alerts_sms_provider', default='MOCK')
    if provider_name == 'AFRICAS_TALKING':
        return AfricasTalkingSMSAdapter()
    return MockSMSAdapter()
