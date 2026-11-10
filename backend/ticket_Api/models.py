
from django.db import models
from django.contrib.auth.models import User
from django.utils import timezone


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
