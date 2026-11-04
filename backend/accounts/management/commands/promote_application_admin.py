from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from accounts.models import UserProfile


class Command(BaseCommand):
    help = (
        "Assign the APPLICATION ADMIN role to an existing user. "
        "This trusted local/server command is intentionally not exposed as an API."
    )

    def add_arguments(self, parser):
        parser.add_argument("--username", required=True)

    @transaction.atomic
    def handle(self, *args, **options):
        User = get_user_model()
        username = options["username"]

        try:
            user = User.objects.select_for_update().get(username=username)
        except User.DoesNotExist:
            raise CommandError(f"User '{username}' does not exist.")

        profile, _ = UserProfile.objects.get_or_create(user=user)
        profile.role = UserProfile.Role.ADMIN
        profile.save(update_fields=["role", "updated_at"])

        self.stdout.write(
            self.style.SUCCESS(
                f"Application ADMIN role assigned to '{user.username}'."
            )
        )
