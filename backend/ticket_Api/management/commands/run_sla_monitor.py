from django.core.management.base import BaseCommand

from ticket_Api.sla_monitor import process_sla_monitoring


class Command(BaseCommand):

    help = "Monitor ticket SLAs and create escalation records."

    def handle(self, *args, **options):

        self.stdout.write("Starting SLA monitoring...")

        results = process_sla_monitoring()

        self.stdout.write(
            self.style.SUCCESS(
                "SLA monitoring completed successfully."
            )
        )

        self.stdout.write(
            f"Tickets checked: {results['tickets_checked']}"
        )

        self.stdout.write(
            f"Response SLA breaches: {results['response_breaches']}"
        )

        self.stdout.write(
            f"Resolution SLA breaches: {results['resolution_breaches']}"
        )

        self.stdout.write(
            f"Escalations created: {results['escalations_created']}"
        )
