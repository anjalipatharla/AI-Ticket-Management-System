
# Django imports
from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.shortcuts import get_object_or_404

# Django REST Framework imports
from rest_framework import generics, status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

# Accounts app imports
from accounts.models import UserProfile
from accounts.permissions import (
    IsAgentOrAbove,
    IsCustomer,
    IsSupportAgent,
)

# Ticket API imports
from .models import Complaint, Ticket, TicketHistory
from .serializers import (
    ComplaintSerializer,
    TicketAssignmentSerializer,
    TicketHistorySerializer,
    TicketSerializer,
    TicketUpdateSerializer,
)


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

            # Record initial ticket creation
            ticket.history.create(
                action=TicketHistory.Action.CREATED,
                changed_by=request.user,
                new_value=ticket.ticket_number,
                comment="Ticket created from customer complaint."
            )

            # Record initial Agent assignment
            ticket.history.create(
                action=TicketHistory.Action.ASSIGNED,
                changed_by=request.user,
                new_value=request.user.username,
                comment="Ticket initially assigned to converting agent."
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


# Helper function: Check whether a user can access a ticket
def get_accessible_ticket(user, ticket_id):

    ticket = get_object_or_404(Ticket, pk=ticket_id)
    profile = getattr(user, "profile", None)

    if not profile:
        raise PermissionDenied("User profile not found.")

    if profile.role == UserProfile.Role.ADMIN:
        return ticket

    if (
        profile.role == UserProfile.Role.CUSTOMER
        and ticket.customer_id == user.id
    ):
        return ticket

    if (
        profile.role == UserProfile.Role.AGENT
        and ticket.assigned_agent_id == user.id
    ):
        return ticket

    raise PermissionDenied("You do not have access to this ticket.")


# 6. Users view individual ticket details
class TicketDetailView(APIView):

    permission_classes = [IsAuthenticated]

    def get(self, request, ticket_id):

        ticket = get_accessible_ticket(request.user, ticket_id)
        serializer = TicketSerializer(ticket)

        return Response(
            serializer.data,
            status=status.HTTP_200_OK
        )


# 7. Admin and assigned Agent update ticket status and priority
class TicketUpdateView(APIView):

    permission_classes = [IsAuthenticated]

    def patch(self, request, ticket_id):

        ticket = get_object_or_404(Ticket, pk=ticket_id)

        profile = getattr(request.user, "profile", None)
        role = profile.role if profile else None

        if role != UserProfile.Role.ADMIN and not (
            role == UserProfile.Role.AGENT
            and ticket.assigned_agent_id == request.user.id
        ):
            return Response(
                {"detail": "You cannot update this ticket."},
                status=status.HTTP_403_FORBIDDEN
            )

        serializer = TicketUpdateSerializer(
            ticket,
            data=request.data,
            partial=True
        )

        serializer.is_valid(raise_exception=True)

        with transaction.atomic():

            old_status = ticket.status
            old_priority = ticket.priority

            ticket = serializer.save()

            # Record status changes
            if old_status != ticket.status:
                ticket.history.create(
                    action=TicketHistory.Action.STATUS_CHANGED,
                    changed_by=request.user,
                    old_value=old_status,
                    new_value=ticket.status
                )

            # Record priority changes
            if old_priority != ticket.priority:
                ticket.history.create(
                    action=TicketHistory.Action.PRIORITY_CHANGED,
                    changed_by=request.user,
                    old_value=old_priority,
                    new_value=ticket.priority
                )

        return Response(
            TicketSerializer(ticket).data,
            status=status.HTTP_200_OK
        )


# 8. Admin assigns or reassigns a ticket to an Agent
class TicketAssignmentView(APIView):

    permission_classes = [IsAuthenticated]

    def patch(self, request, ticket_id):

        profile = getattr(request.user, "profile", None)

        if not profile or profile.role != UserProfile.Role.ADMIN:
            return Response(
                {"detail": "Only Admin can assign or reassign tickets."},
                status=status.HTTP_403_FORBIDDEN
            )

        ticket = get_object_or_404(Ticket, pk=ticket_id)

        serializer = TicketAssignmentSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        new_agent = serializer.validated_data["agent"]
        old_agent = ticket.assigned_agent

        if old_agent.id == new_agent.id:
            return Response(
                {"detail": "Ticket is already assigned to this Agent."},
                status=status.HTTP_400_BAD_REQUEST
            )

        with transaction.atomic():

            ticket.assigned_agent = new_agent
            ticket.save(update_fields=["assigned_agent", "updated_at"])

            # Record Agent reassignment
            ticket.history.create(
                action=TicketHistory.Action.REASSIGNED,
                changed_by=request.user,
                old_value=old_agent.username,
                new_value=new_agent.username
            )

        return Response(
            TicketSerializer(ticket).data,
            status=status.HTTP_200_OK
        )


# 9. Users view ticket history
class TicketHistoryView(APIView):

    permission_classes = [IsAuthenticated]

    def get(self, request, ticket_id):

        ticket = get_accessible_ticket(request.user, ticket_id)

        history = ticket.history.select_related(
            "changed_by",
            "ticket"
        )

        serializer = TicketHistorySerializer(
            history,
            many=True
        )

        return Response(
            serializer.data,
            status=status.HTTP_200_OK
        )
