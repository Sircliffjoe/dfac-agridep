from rest_framework import permissions

class ScopedQuerySetMixin:
    """
    Enforces row-level isolation based on the authenticated user's role.
    If an external role accesses a record outside its relationship,
    the queryset returns empty (resulting in 404 Not Found), preventing ID enumeration.
    """
    def get_queryset(self):
        user = self.request.user
        qs = super().get_queryset()

        if not user or not user.is_authenticated:
            return qs.none()

        if user.is_superuser or getattr(user, 'role', '') == 'DFAC_ADMIN':
            return qs

        role = getattr(user, 'role', '')

        # Scoping per model and role
        model_name = qs.model.__name__

        if role == 'FIELD_OFFICER':
            if hasattr(qs.model, 'assigned_officer'):
                return qs.filter(assigned_officer=user)
            elif hasattr(qs.model, 'farmer') and hasattr(qs.model.farmer.field.related_model, 'assigned_officer'):
                return qs.filter(farmer__assigned_officer=user)
            elif hasattr(qs.model, 'farm') and hasattr(qs.model.farm.field.related_model, 'farmer'):
                return qs.filter(farm__farmer__assigned_officer=user)

        elif role == 'LENDER':
            if hasattr(qs.model, 'lender'):
                return qs.filter(lender__user=user)
            elif hasattr(qs.model, 'loan') and hasattr(qs.model.loan.field.related_model, 'lender'):
                return qs.filter(loan__lender__user=user)

        elif role == 'BUYER':
            if hasattr(qs.model, 'buyer'):
                return qs.filter(buyer__user=user)
            elif hasattr(qs.model, 'demand') and hasattr(qs.model.demand.field.related_model, 'buyer'):
                return qs.filter(demand__buyer__user=user)

        elif role == 'FARMER':
            if hasattr(qs.model, 'farmer'):
                return qs.filter(farmer__user=user)
            elif hasattr(qs.model, 'user'):
                return qs.filter(user=user)

        return qs

class IsDFACAdmin(permissions.BasePermission):
    """Allows access only to DFAC administrators."""
    def has_permission(self, request, view):
        return bool(request.user and request.user.is_authenticated and (request.user.is_superuser or getattr(request.user, 'role', '') == 'DFAC_ADMIN'))

class IsFieldOfficer(permissions.BasePermission):
    """Allows access to field officers and DFAC admins."""
    def has_permission(self, request, view):
        return bool(request.user and request.user.is_authenticated and (getattr(request.user, 'role', '') in ('FIELD_OFFICER', 'DFAC_ADMIN') or request.user.is_superuser))

class IsLender(permissions.BasePermission):
    """Allows access to verified lenders."""
    def has_permission(self, request, view):
        return bool(request.user and request.user.is_authenticated and (getattr(request.user, 'role', '') in ('LENDER', 'DFAC_ADMIN') or request.user.is_superuser))

class IsBuyer(permissions.BasePermission):
    """Allows access to verified buyers."""
    def has_permission(self, request, view):
        return bool(request.user and request.user.is_authenticated and (getattr(request.user, 'role', '') in ('BUYER', 'DFAC_ADMIN') or request.user.is_superuser))

class IsTrainer(permissions.BasePermission):
    """Allows access to trainers."""
    def has_permission(self, request, view):
        return bool(request.user and request.user.is_authenticated and (getattr(request.user, 'role', '') in ('TRAINER', 'DFAC_ADMIN') or request.user.is_superuser))

class IsFarmer(permissions.BasePermission):
    """Allows access to farmers."""
    def has_permission(self, request, view):
        return bool(request.user and request.user.is_authenticated and (getattr(request.user, 'role', '') in ('FARMER', 'DFAC_ADMIN') or request.user.is_superuser))
