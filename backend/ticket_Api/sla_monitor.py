
from datetime import timedelta

from django.db import transaction
from django.utils import timezone

from .models import (
    Ticket,
    TicketSLA,
    TicketEscalation,
    TicketHistory,
)


# Project escalation thresholds
LEVEL_2_AFTER_MINUTES = 30
LEVEL_3_AFTER_MINUTES = 60


def create_sla_escalations(sla, reason, overdue_duration):

    ticket = sla.ticket
    levels = [TicketEscalation.Level.LEVEL_1]

    # Add Level 2 after 30 minutes of overdue time
    if overdue_duration >= timedelta(
        minutes=LEVEL_2_AFTER_MINUTES
    ):
        levels.append(TicketEscalation.Level.LEVEL_2)

    # Add Level 3 after 60 minutes of overdue time
    if overdue_duration >= timedelta(
        minutes=LEVEL_3_AFTER_MINUTES
    ):
        levels.append(TicketEscalation.Level.LEVEL_3)

    created_count = 0

    for level in levels:

        escalation, created = TicketEscalation.objects.get_or_create(
            ticket=ticket,
            level=level,
            reason=reason,
            defaults={
                "details": (
                    f"{reason.replace('_', ' ').title()} "
                    f"for ticket {ticket.ticket_number}. "
                    f"Overdue duration: {int(overdue_duration.total_seconds() // 60)} minutes."
                )
            }
        )

        if created:
            created_count += 1

            TicketHistory.objects.create(
                ticket=ticket,
                action=TicketHistory.Action.ESCALATION_CREATED,
                old_value="",
                new_value=level,
                comment=escalation.details,
                changed_by=None
            )

    return created_count


def process_sla_monitoring(now=None):

    if now is None:
        now = timezone.now()

    results = {
        "response_breaches": 0,
        "resolution_breaches": 0,
        "escalations_created": 0,
        "tickets_checked": 0,
    }

    sla_ids = TicketSLA.objects.values_list(
        "id",
        flat=True
    )

    for sla_id in sla_ids:

        with transaction.atomic():

            sla = (
                TicketSLA.objects
                .select_for_update()
                .select_related("ticket")
                .get(id=sla_id)
            )

            ticket = sla.ticket
            results["tickets_checked"] += 1

            # ---------------------------------
            # 1. Check Response SLA
            # ---------------------------------

            if sla.first_response_at:

                # First response was recorded.
                if sla.first_response_at <= sla.response_deadline:

                    sla.response_status = TicketSLA.Status.MET

                else:

                    sla.response_status = TicketSLA.Status.BREACHED
                    results["response_breaches"] += 1

                    overdue_duration = (
                        sla.first_response_at - sla.response_deadline
                    )

                    results["escalations_created"] += (
                        create_sla_escalations(
                            sla,
                            TicketEscalation.Reason.RESPONSE_BREACHED,
                            overdue_duration
                        )
                    )

            elif now > sla.response_deadline:

                # No response before deadline.
                sla.response_status = TicketSLA.Status.BREACHED

                overdue_duration = now - sla.response_deadline

                results["escalations_created"] += (
                    create_sla_escalations(
                        sla,
                        TicketEscalation.Reason.RESPONSE_BREACHED,
                        overdue_duration
                    )
                )

                results["response_breaches"] += 1

            # ---------------------------------
            # 2. Check Resolution SLA
            # ---------------------------------

            if sla.resolved_at:

                # Ticket was resolved or closed.
                if sla.resolved_at <= sla.resolution_deadline:

                    sla.resolution_status = TicketSLA.Status.MET

                else:

                    sla.resolution_status = TicketSLA.Status.BREACHED
                    results["resolution_breaches"] += 1

                    overdue_duration = (
                        sla.resolved_at - sla.resolution_deadline
                    )

                    results["escalations_created"] += (
                        create_sla_escalations(
                            sla,
                            TicketEscalation.Reason.RESOLUTION_BREACHED,
                            overdue_duration
                        )
                    )

            elif ticket.status not in [
                Ticket.Status.RESOLVED,
                Ticket.Status.CLOSED
            ] and now > sla.resolution_deadline:

                # Ticket remains unresolved after deadline.
                sla.resolution_status = TicketSLA.Status.BREACHED

                overdue_duration = now - sla.resolution_deadline

                results["escalations_created"] += (
                    create_sla_escalations(
                        sla,
                        TicketEscalation.Reason.RESOLUTION_BREACHED,
                        overdue_duration
                    )
                )

                results["resolution_breaches"] += 1

            # ---------------------------------
            # 3. Record last monitoring time
            # ---------------------------------

            sla.last_checked_at = now

            sla.save(
                update_fields=[
                    "response_status",
                    "resolution_status",
                    "last_checked_at",
                    "updated_at",
                ]
            )

    return results
