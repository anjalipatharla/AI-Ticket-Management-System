
from django.db import models
from django.contrib.auth.models import User
from django.utils import timezone
from django.core.validators import MinValueValidator


class Complaint(models.Model):

    class Category(models.TextChoices):
        BILLING = "BILLING", "Billing"
        TECHNICAL = "TECHNICAL", "Technical"
        ACCOUNT = "ACCOUNT", "Account"
        OTHER = "OTHER", "Other"

    class Status(models.TextChoices):
        PENDING = "PENDING", "Pending"
        CONVERTED = "CONVERTED", "Converted to Ticket"

    customer = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="complaints"
    )

    subject = models.CharField(max_length=200)

    description = models.TextField()

    category = models.CharField(
        max_length=20,
        choices=Category.choices
    )

    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.PENDING
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Complaint #{self.id} - {self.subject}"


class Ticket(models.Model):

    class Priority(models.TextChoices):
        LOW = "LOW", "Low"
        MEDIUM = "MEDIUM", "Medium"
        HIGH = "HIGH", "High"
        CRITICAL = "CRITICAL", "Critical"

    class Status(models.TextChoices):
        OPEN = "OPEN", "Open"
        IN_PROGRESS = "IN_PROGRESS", "In Progress"
        RESOLVED = "RESOLVED", "Resolved"
        CLOSED = "CLOSED", "Closed"

    CATEGORY_PREFIX = {
        "BILLING": "BILL",
        "TECHNICAL": "TECH",
        "ACCOUNT": "ACCT",
        "OTHER": "GEN",
    }

    ticket_number = models.CharField(
        max_length=30,
        unique=True,
        null=True,
        blank=True,
        editable=False
    )

    complaint = models.OneToOneField(
        Complaint,
        on_delete=models.PROTECT,
        related_name="ticket"
    )

    customer = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="customer_tickets"
    )

    assigned_agent = models.ForeignKey(
        User,
        on_delete=models.PROTECT,
        related_name="assigned_tickets"
    )

    subject = models.CharField(max_length=200)
    description = models.TextField()

    category = models.CharField(
        max_length=20,
        choices=Complaint.Category.choices
    )

    priority = models.CharField(
        max_length=20,
        choices=Priority.choices,
        default=Priority.MEDIUM
    )

    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.OPEN
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def save(self, *args, **kwargs):

        if self.pk is None:
            super().save(*args, **kwargs)

            if not self.ticket_number:
                prefix = self.CATEGORY_PREFIX[self.category]
                year = timezone.localdate().year

                self.ticket_number = (
                    f"{prefix}-{year}-{self.pk:06d}"
                )

                super().save(update_fields=["ticket_number"])

            return

        super().save(*args, **kwargs)

    def __str__(self):
        return self.ticket_number or f"Ticket #{self.pk}"


class TicketHistory(models.Model):

    class Action(models.TextChoices):
        CREATED = "CREATED", "Ticket Created"
        STATUS_CHANGED = "STATUS_CHANGED", "Status Changed"
        PRIORITY_CHANGED = "PRIORITY_CHANGED", "Priority Changed"
        ASSIGNED = "ASSIGNED", "Agent Assigned"
        REASSIGNED = "REASSIGNED", "Agent Reassigned"
        FIRST_RESPONSE_RECORDED = "FIRST_RESPONSE_RECORDED", "First Response Recorded"
        ESCALATION_CREATED = "ESCALATION_CREATED", "Escalation Created"

    ticket = models.ForeignKey(
        Ticket,
        on_delete=models.CASCADE,
        related_name="history"
    )

    action = models.CharField(
        max_length=30,
        choices=Action.choices
    )

    changed_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="ticket_history_actions"
    )

    old_value = models.CharField(
        max_length=100,
        blank=True
    )

    new_value = models.CharField(
        max_length=100,
        blank=True
    )

    comment = models.TextField(blank=True)

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at", "id"]

    def __str__(self):
        return f"{self.ticket.ticket_number} - {self.action}"


# 4. SLA Policy: Defines service deadlines for each ticket priority
class SLAPolicy(models.Model):

    priority = models.CharField(
        max_length=20,
        choices=Ticket.Priority.choices,
        unique=True
    )

    response_time_minutes = models.PositiveIntegerField(
        validators=[MinValueValidator(1)]
    )

    resolution_time_minutes = models.PositiveIntegerField(
        validators=[MinValueValidator(1)]
    )

    is_active = models.BooleanField(default=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["priority"]

    def __str__(self):
        return f"{self.priority} - SLA Policy"


# 5. Ticket SLA: Tracks deadlines and SLA performance for each ticket
class TicketSLA(models.Model):

    class Status(models.TextChoices):
        PENDING = "PENDING", "Pending"
        MET = "MET", "Met"
        BREACHED = "BREACHED", "Breached"

    ticket = models.OneToOneField(
        Ticket,
        on_delete=models.CASCADE,
        related_name="sla"
    )

    policy = models.ForeignKey(
        SLAPolicy,
        on_delete=models.PROTECT,
        related_name="ticket_slas"
    )

    # Snapshot of policy targets at ticket creation
    response_target_minutes = models.PositiveIntegerField()
    resolution_target_minutes = models.PositiveIntegerField()

    response_deadline = models.DateTimeField()
    resolution_deadline = models.DateTimeField()

    first_response_at = models.DateTimeField(
        null=True,
        blank=True
    )

    resolved_at = models.DateTimeField(
        null=True,
        blank=True
    )

    response_status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.PENDING
    )

    resolution_status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.PENDING
    )

    last_checked_at = models.DateTimeField(
        null=True,
        blank=True
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"SLA for {self.ticket.ticket_number}"


# 6. Ticket Escalation: Records escalation events
class TicketEscalation(models.Model):

    class Level(models.TextChoices):
        LEVEL_1 = "LEVEL_1", "Level 1"
        LEVEL_2 = "LEVEL_2", "Level 2"
        LEVEL_3 = "LEVEL_3", "Level 3"

    class Reason(models.TextChoices):
        RESPONSE_BREACHED = "RESPONSE_BREACHED", "Response SLA Breached"
        RESOLUTION_BREACHED = "RESOLUTION_BREACHED", "Resolution SLA Breached"
        MANUAL = "MANUAL", "Manual Escalation"

    class Status(models.TextChoices):
        OPEN = "OPEN", "Open"
        ACKNOWLEDGED = "ACKNOWLEDGED", "Acknowledged"
        RESOLVED = "RESOLVED", "Resolved"

    ticket = models.ForeignKey(
        Ticket,
        on_delete=models.CASCADE,
        related_name="escalations"
    )

    level = models.CharField(
        max_length=20,
        choices=Level.choices
    )

    reason = models.CharField(
        max_length=30,
        choices=Reason.choices
    )

    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.OPEN
    )

    details = models.TextField(blank=True)

    triggered_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="triggered_ticket_escalations"
    )

    triggered_at = models.DateTimeField(auto_now_add=True)

    acknowledged_at = models.DateTimeField(
        null=True,
        blank=True
    )

    resolved_at = models.DateTimeField(
        null=True,
        blank=True
    )

    class Meta:
        ordering = ["-triggered_at"]

        constraints = [
            models.UniqueConstraint(
                fields=["ticket", "level", "reason"],
                name="unique_ticket_escalation_level_reason"
            )
        ]

    def __str__(self):
        return f"{self.ticket.ticket_number} - {self.level}"
