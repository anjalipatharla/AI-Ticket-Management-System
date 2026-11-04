from rest_framework.permissions import BasePermission

from .models import UserProfile


class HasApplicationRole(BasePermission):
    """
    Base permission for application roles.

    A Django superuser is not automatically an Application Admin. The
    application role must be assigned explicitly to the user's profile.
    """

    allowed_roles = frozenset()

    def has_permission(self, request, view):
        user = request.user

        if not user or not user.is_authenticated or not user.is_active:
            return False

        profile = getattr(user, "profile", None)
        return bool(profile and profile.role in self.allowed_roles)

    def has_object_permission(self, request, view, obj):
        return self.has_permission(request, view)


class IsCustomer(HasApplicationRole):
    allowed_roles = {UserProfile.Role.CUSTOMER}


class IsSupportAgent(HasApplicationRole):
    allowed_roles = {UserProfile.Role.AGENT}


class IsManager(HasApplicationRole):
    allowed_roles = {UserProfile.Role.MANAGER}


class IsApplicationAdmin(HasApplicationRole):
    allowed_roles = {UserProfile.Role.ADMIN}


class IsManagerOrAdmin(HasApplicationRole):
    allowed_roles = {
        UserProfile.Role.MANAGER,
        UserProfile.Role.ADMIN,
    }


class IsAgentOrAbove(HasApplicationRole):
    allowed_roles = {
        UserProfile.Role.AGENT,
        UserProfile.Role.MANAGER,
        UserProfile.Role.ADMIN,
    }
