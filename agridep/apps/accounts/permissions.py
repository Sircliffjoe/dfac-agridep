from functools import wraps
from django.shortcuts import redirect
from django.contrib import messages
from django.core.exceptions import PermissionDenied
from agridep.apps.accounts.models import UserRole

# Role Hierarchy / Portal Mapping
ROLE_PORTAL_MAP = {
    UserRole.DFAC_ADMIN: 'admin-console',
    UserRole.FIELD_OFFICER: 'fieldops-portal',
    UserRole.TRAINER: 'trainer-portal',
    UserRole.LENDER: 'lender-portal',
    UserRole.BUYER: 'buyer-portal',
    UserRole.FARMER: 'farmer-portal',
}

ROLE_PERMISSIONS = {
    UserRole.DFAC_ADMIN: [
        'admin-console', 'cockpit', 'fieldops-portal', 'trainer-portal',
        'lender-portal', 'buyer-portal', 'farmer-portal', 'reporting-portal',
        'inputs-portal', 'ussd-simulator', 'portal-profile'
    ],
    UserRole.FIELD_OFFICER: [
        'fieldops-portal', 'farmer-portal', 'ussd-simulator', 'portal-profile'
    ],
    UserRole.TRAINER: [
        'trainer-portal', 'verify-certificate', 'portal-profile'
    ],
    UserRole.LENDER: [
        'lender-portal', 'portal-profile'
    ],
    UserRole.BUYER: [
        'buyer-portal', 'portal-profile'
    ],
    UserRole.FARMER: [
        'farmer-portal', 'verify-certificate', 'portal-profile'
    ],
}


def get_user_dashboard_url_name(user) -> str:
    """Returns the primary dashboard URL name for a given user."""
    if not user.is_authenticated:
        return 'portal-login'
    
    role = getattr(user, 'role', None)
    if user.is_superuser or role == UserRole.DFAC_ADMIN:
        return 'cockpit'
    
    return ROLE_PORTAL_MAP.get(role, 'home')


def role_required(*allowed_roles):
    """
    Decorator for views that checks whether a user has one of the allowed roles.
    DFAC_ADMIN and superusers always have bypass privileges.
    """
    def decorator(view_func):
        @wraps(view_func)
        def _wrapped_view(request, *args, **kwargs):
            if not request.user.is_authenticated:
                messages.warning(request, "Please sign in to access this operational desk.")
                return redirect(f"/login/?next={request.path}")
            
            user_role = getattr(request.user, 'role', None)
            
            # Superusers and DFAC Admins have full access
            if request.user.is_superuser or user_role == UserRole.DFAC_ADMIN:
                return view_func(request, *args, **kwargs)
            
            if user_role in allowed_roles:
                return view_func(request, *args, **kwargs)
            
            # Unauthorized role
            role_label = getattr(request.user, 'get_role_display', lambda: user_role)()
            messages.error(
                request,
                f"Access Restricted: Your account role ({role_label}) does not have permission to view that desk. Redirected to your home dashboard."
            )
            return redirect(get_user_dashboard_url_name(request.user))
        return _wrapped_view
    return decorator


def admin_required(view_func):
    """Restricts access strictly to DFAC Administrators and Superusers."""
    return role_required(UserRole.DFAC_ADMIN)(view_func)
