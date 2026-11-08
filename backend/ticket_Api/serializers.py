
from rest_framework import serializers
from .models import Complaint, Ticket


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
