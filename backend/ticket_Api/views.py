
from django.db import transaction
from django.shortcuts import get_object_or_404

from rest_framework import generics, status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from accounts.models import UserProfile
from accounts.permissions import IsCustomer, IsAgentOrAbove, IsSupportAgent
from .models import Complaint, Ticket
from .serializers import ComplaintSerializer, TicketSerializer


# 1. Customer submits a complaint
class ComplaintCreateView(generics.CreateAPIView):

    serializer_class = ComplaintSerializer
    permission_classes = [IsCustomer]

    def perform_create(self, serializer):
        serializer.save(customer=self.request.user)


# 2. Customer views their own complaints
class MyComplaintsView(generics.ListAPIView):

    serializer_class = ComplaintSerializer
    permission_classes = [IsCustomer]

    def get_queryset(self):
        return Complaint.objects.filter(
            customer=self.request.user
        ).order_by("-created_at")


# 3. Agent views pending customer complaints
class PendingComplaintsView(generics.ListAPIView):

    serializer_class = ComplaintSerializer
    permission_classes = [IsAgentOrAbove]

    def get_queryset(self):
        return Complaint.objects.filter(
            status=Complaint.Status.PENDING
        ).select_related("customer").order_by("-created_at")


# 4. Agent converts a complaint into a ticket
class ConvertComplaintToTicketView(APIView):

    permission_classes = [IsSupportAgent]

    def post(self, request, complaint_id):

        priority = request.data.get(
            "priority",
            Ticket.Priority.MEDIUM
        )

        if priority not in Ticket.Priority.values:
            return Response(
                {"error": "Invalid ticket priority."},
                status=status.HTTP_400_BAD_REQUEST
            )

        with transaction.atomic():

            complaint = get_object_or_404(
                Complaint.objects.select_for_update(),
                id=complaint_id
            )

            if (
                complaint.status != Complaint.Status.PENDING
                or Ticket.objects.filter(complaint=complaint).exists()
            ):
                return Response(
                    {"error": "This complaint has already been converted."},
                    status=status.HTTP_400_BAD_REQUEST
                )

            ticket = Ticket.objects.create(
                complaint=complaint,
                customer=complaint.customer,
                assigned_agent=request.user,
                subject=complaint.subject,
                description=complaint.description,
                category=complaint.category,
                priority=priority
            )

            complaint.status = Complaint.Status.CONVERTED
            complaint.save(update_fields=["status", "updated_at"])

        return Response(
            TicketSerializer(ticket).data,
            status=status.HTTP_201_CREATED
        )


# 5. Users view tickets according to their application role
class TicketListView(generics.ListAPIView):

    serializer_class = TicketSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):

        user = self.request.user
        profile = getattr(user, "profile", None)

        if not profile:
            return Ticket.objects.none()

        if profile.role == UserProfile.Role.CUSTOMER:
            return Ticket.objects.filter(
                customer=user
            ).order_by("-created_at")

        if profile.role == UserProfile.Role.AGENT:
            return Ticket.objects.filter(
                assigned_agent=user
            ).order_by("-created_at")

        if profile.role == UserProfile.Role.ADMIN:
            return Ticket.objects.all().order_by("-created_at")

        return Ticket.objects.none()
