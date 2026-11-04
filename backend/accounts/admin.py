from django.contrib import admin

from .models import GoogleIdentity, UserProfile


@admin.register(UserProfile)
class UserProfileAdmin(admin.ModelAdmin):
    list_display = ("id", "user", "role", "phone_number", "created_at")
    list_filter = ("role", "created_at")
    search_fields = ("user__username", "user__email", "phone_number")
    readonly_fields = ("created_at", "updated_at")

    # Django superusers bootstrap and administer application roles.
    # Application Admin users use the protected API, not Django admin.
    def has_module_permission(self, request):
        return request.user.is_superuser

    def has_view_permission(self, request, obj=None):
        return request.user.is_superuser

    def has_add_permission(self, request):
        return request.user.is_superuser

    def has_change_permission(self, request, obj=None):
        return request.user.is_superuser

    def has_delete_permission(self, request, obj=None):
        return request.user.is_superuser


@admin.register(GoogleIdentity)
class GoogleIdentityAdmin(admin.ModelAdmin):
    list_display = ("id", "user", "email", "created_at")
    search_fields = ("user__username", "email", "google_sub")
    readonly_fields = ("user", "google_sub", "email", "created_at")

    def has_module_permission(self, request):
        return request.user.is_superuser

    def has_view_permission(self, request, obj=None):
        return request.user.is_superuser

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
