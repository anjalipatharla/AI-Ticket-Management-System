from django.contrib import admin
from .models import GoogleIdentity, UserProfile


@admin.register(UserProfile)
class UserProfileAdmin(admin.ModelAdmin):
    list_display = ("id", "user", "role", "phone_number", "created_at")
    list_filter = ("role", "created_at")
    search_fields = ("user__username", "user__email", "phone_number")
    readonly_fields = ("created_at", "updated_at")


@admin.register(GoogleIdentity)
class GoogleIdentityAdmin(admin.ModelAdmin):
    list_display = ("id", "user", "email", "created_at")
    search_fields = ("user__username", "email", "google_sub")
    readonly_fields = ("google_sub", "email", "created_at")
