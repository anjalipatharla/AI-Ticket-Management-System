
from rest_framework import serializers
from .models import Complaint, Ticket, TicketHistory
from accounts.models import UserProfile
from django.contrib.auth.models import User


class ComplaintSerializer(serializers.ModelSerializer):

    customer_username = serializers.CharField(
        source="customer.username",
        read_only=True
    )

    class Meta:
        model = Complaint

        fields = [
            "id",
            "customer_username",
            "subject",
            "description",
            "category",
            "status",
            "created_at",
            "updated_at",
        ]

        read_only_fields = [
            "id",
            "customer_username",
            "status",
            "created_at",
            "updated_at",
        ]


class TicketSerializer(serializers.ModelSerializer):

    complaint_id = serializers.IntegerField(
        source="complaint.id",
        read_only=True
    )

    customer_username = serializers.CharField(
        source="customer.username",
        read_only=True
    )

    assigned_agent_username = serializers.CharField(
        source="assigned_agent.username",
        read_only=True
    )

    class Meta:
        model = Ticket

        fields = [
            "id",
            "ticket_number",
            "complaint_id",
            "customer_username",
            "assigned_agent_username",
            "subject",
            "description",
            "category",
            "priority",
            "status",
            "created_at",
            "updated_at",
        ]

        read_only_fields = fields


class TicketUpdateSerializer(serializers.ModelSerializer):
    class Meta:
        model = Ticket
        fields = ["status", "priority"]


class TicketAssignmentSerializer(serializers.Serializer):
    agent_id = serializers.PrimaryKeyRelatedField(
        source="agent",
        queryset=User.objects.filter(is_active=True)
    )

    def validate_agent_id(self, agent):
        profile = getattr(agent, "profile", None)

        if not profile or profile.role != UserProfile.Role.AGENT:
            raise serializers.ValidationError(
                "The selected user is not an active support agent."
            )

        return agent


class TicketHistorySerializer(serializers.ModelSerializer):
    ticket_number = serializers.CharField(
        source="ticket.ticket_number",
        read_only=True
    )
    changed_by_username = serializers.CharField(
        source="changed_by.username",
        read_only=True,
        allow_null=True
    )

    class Meta:
        model = TicketHistory
        fields = [
            "id",
            "ticket",
            "ticket_number",
            "action",
            "changed_by",
            "changed_by_username",
            "old_value",
            "new_value",
            "comment",
            "created_at",
        ]
