from typing import Optional, Dict, Any
from .models import AuditEvent, AuditAction

def log_audit_event(
    action: str,
    resource_type: str,
    resource_id: str,
    user=None,
    details: Optional[Dict[str, Any]] = None,
    request=None
) -> AuditEvent:
    """Helper service to log security and data compliance events."""
    ip_address = None
    user_agent = ''

    if request:
        x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
        if x_forwarded_for:
            ip_address = x_forwarded_for.split(',')[0].strip()
        else:
            ip_address = request.META.get('REMOTE_ADDR')
        user_agent = request.META.get('HTTP_USER_AGENT', '')[:255]
        if not user and request.user and request.user.is_authenticated:
            user = request.user

    return AuditEvent.objects.create(
        user=user,
        action=action,
        resource_type=resource_type,
        resource_id=str(resource_id),
        ip_address=ip_address,
        user_agent=user_agent,
        details=details or {}
    )
