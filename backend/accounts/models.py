
from django.db import models
from django.contrib.auth.models import User


class UserProfile(models.Model):

    class Role(models.TextChoices):
        CUSTOMER = "CUSTOMER", "Customer"
        AGENT = "AGENT", "Support Agent"
        MANAGER = "MANAGER", "Manager"
        ADMIN = "ADMIN", "Application Admin"

    user = models.OneToOneField(
        User,
        on_delete=models.CASCADE,
        related_name="profile"
    )

    role = models.CharField(
        max_length=20,
        choices=Role.choices,
        default=Role.CUSTOMER
    )

    phone_number = models.CharField(
        max_length=15,
        blank=True,
        null=True
    )

    profile_picture = models.URLField(
        blank=True,
        null=True
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.user.username} - {self.role}"

class GoogleIdentity(models.Model):

    user = models.OneToOneField(
        User,
        on_delete=models.CASCADE,
        related_name="google_identity"
    )

    google_sub = models.CharField(
        max_length=255,
        unique=True
    )

    email = models.EmailField()

    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Google identity - {self.user.username}"