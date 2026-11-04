
from django.contrib import admin
from .models import UserProfile


@admin.register(UserProfile)
class UserProfileAdmin(admin.ModelAdmin):

    list_display = (
        "id",
        "user",
        "role",
        "phone_number",
        "created_at",
    )

    list_filter = ("role", "created_at")

    search_fields = (
        "user__username",
        "user__email",
        "phone_number",
    )

    readonly_fields = ("created_at", "updated_at")
