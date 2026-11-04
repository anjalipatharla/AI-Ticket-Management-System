from rest_framework.permissions import BasePermission

from .models import UserProfile


class HasApplicationRole(BasePermission):
    """Require an authenticated user with one of the configured app roles."""

    allowed_roles = frozenset()

    def has_permission(self, request, view):
        user = request.user
        if not user or not user.is_authenticated:
            return False
        try:
            role = user.profile.role
        except UserProfile.DoesNotExist:
            return False
        return role in self.allowed_roles


class IsCustomer(HasApplicationRole):
    allowed_roles = frozenset({UserProfile.Role.CUSTOMER})


class IsSupportAgent(HasApplicationRole):
    allowed_roles = frozenset({UserProfile.Role.AGENT})


class IsManager(HasApplicationRole):
    allowed_roles = frozenset({UserProfile.Role.MANAGER})


class IsApplicationAdmin(HasApplicationRole):
    allowed_roles = frozenset({UserProfile.Role.ADMIN})


class IsAgentOrAbove(HasApplicationRole):
    allowed_roles = frozenset({
        UserProfile.Role.AGENT,
        UserProfile.Role.MANAGER,
        UserProfile.Role.ADMIN,
    })


class IsManagerOrAdmin(HasApplicationRole):
    allowed_roles = frozenset({
        UserProfile.Role.MANAGER,
        UserProfile.Role.ADMIN,
    })


class IsOwnerOrSupportTeam(HasApplicationRole):
    """
    Object permission for resources exposing customer_id.
    Customer list endpoints must also filter their querysets by request.user.
    """

    allowed_roles = frozenset({
        UserProfile.Role.AGENT,
        UserProfile.Role.MANAGER,
        UserProfile.Role.ADMIN,
    })

    def has_object_permission(self, request, view, obj):
        user = request.user
        if not user or not user.is_authenticated:
            return False
        if getattr(obj, "customer_id", None) == user.pk:
            return True
        return self.has_permission(request, view)
