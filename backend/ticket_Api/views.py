
# Standard Python imports
from datetime import timedelta
from django.utils import timezone

# Django imports
from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.shortcuts import get_object_or_404
from .ai_services.complaint_classifier import classify_complaint
from .ai_services.reply_generator import generate_reply

# Django REST Framework imports
from rest_framework import generics, status
from rest_framework.permissions import IsAuthenticated
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response
from rest_framework.views import APIView

# Accounts app imports
from accounts.models import UserProfile
from accounts.permissions import (
    IsAgentOrAbove,
    IsCustomer,
    IsSupportAgent,
    IsApplicationAdmin,
)

# Ticket API model imports
from .models import (
    Complaint,
    Ticket,
    TicketHistory,
    SLAPolicy,
    TicketSLA,
    KnowledgeCategory,
    KnowledgeArticle,
    FAQ,
    TicketMessage,
)

# Ticket API serializer imports
from .serializers import (
    ComplaintSerializer,
    TicketAssignmentSerializer,
    TicketHistorySerializer,
    TicketSerializer,
    TicketUpdateSerializer,
    KnowledgeCategorySerializer,
    KnowledgeArticleSerializer,
    FAQSerializer,
    TicketMessageSerializer,
)

import logging
logger = logging.getLogger(__name__)


# 1. Customer submits a complaint

class ComplaintCreateView(generics.CreateAPIView):

    serializer_class = ComplaintSerializer
    permission_classes = [IsCustomer]

    def create(self, request, *args, **kwargs):

        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        # 1. Get complaint details
        subject = serializer.validated_data["subject"]
        description = serializer.validated_data["description"]

        # 2. Ask Gemini to classify the complaint
        try:
            ai_result = classify_complaint(subject, description)
        except Exception:
            logger.exception("Gemini AI classification failed.")

            ai_result = {
                "category": "OTHER",
                "priority": "MEDIUM",
                "sentiment": "NEUTRAL",
                "summary": "AI classification is currently unavailable."
            }

        # 3. Save complaint using AI-suggested category
        complaint = serializer.save(
            customer=request.user,
            category=ai_result["category"],
            ai_suggested_priority=ai_result["priority"],
            ai_sentiment=ai_result["sentiment"],
            ai_summary=ai_result["summary"]
        )

        # 4. Prepare API response
        response_data = {
            "complaint": self.get_serializer(complaint).data,
            "ai_classification": ai_result
        }

        headers = self.get_success_headers(serializer.data)

        return Response(response_data, status=status.HTTP_201_CREATED, headers=headers)


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
#    and automatically creates its SLA record
class ConvertComplaintToTicketView(APIView):

    permission_classes = [IsSupportAgent]

    def post(self, request, complaint_id):

        with transaction.atomic():

            # Get and lock the complaint
            complaint = get_object_or_404(
                Complaint.objects.select_for_update(),
                id=complaint_id
            )

            # Get priority from Agent, otherwise use Gemini suggestion
            priority = request.data.get("priority")

            if priority is None:
                priority = complaint.ai_suggested_priority or Ticket.Priority.MEDIUM

            # Validate priority
            if priority not in Ticket.Priority.values:
                return Response(
                    {"error": "Invalid ticket priority."},
                    status=status.HTTP_400_BAD_REQUEST
                )

            # Prevent duplicate conversion
            if (
                complaint.status != Complaint.Status.PENDING
                or Ticket.objects.filter(complaint=complaint).exists()
            ):
                return Response(
                    {"error": "This complaint has already been converted."},
                    status=status.HTTP_400_BAD_REQUEST
                )

            # 1. Find the active SLA policy BEFORE creating the ticket
            sla_policy = SLAPolicy.objects.filter(
                priority=priority,
                is_active=True
            ).first()

            if not sla_policy:
                return Response(
                    {
                        "error": (
                            f"No active SLA policy configured "
                            f"for {priority} priority."
                        )
                    },
                    status=status.HTTP_400_BAD_REQUEST
                )

            # 2. Create the ticket
            ticket = Ticket.objects.create(
                complaint=complaint,
                customer=complaint.customer,
                assigned_agent=request.user,
                subject=complaint.subject,
                description=complaint.description,
                category=complaint.category,
                priority=priority
            )

            # 3. Calculate response and resolution deadlines
            response_deadline = (
                ticket.created_at
                + timedelta(
                    minutes=sla_policy.response_time_minutes
                )
            )

            resolution_deadline = (
                ticket.created_at
                + timedelta(
                    minutes=sla_policy.resolution_time_minutes
                )
            )

            # 4. Create SLA tracking record
            TicketSLA.objects.create(
                ticket=ticket,
                policy=sla_policy,
                response_target_minutes=(
                    sla_policy.response_time_minutes
                ),
                resolution_target_minutes=(
                    sla_policy.resolution_time_minutes
                ),
                response_deadline=response_deadline,
                resolution_deadline=resolution_deadline
            )

            # 5. Record initial ticket creation
            ticket.history.create(
                action=TicketHistory.Action.CREATED,
                changed_by=request.user,
                new_value=ticket.ticket_number,
                comment="Ticket created from customer complaint."
            )

            # Record priority selection during ticket creation
            ticket.history.create(
                action=TicketHistory.Action.PRIORITY_CHANGED,
                changed_by=request.user,
                old_value=complaint.ai_suggested_priority or "NONE",
                new_value=priority,
                comment=(
                    "Agent overrode AI-suggested priority."
                    if request.data.get("priority") is not None
                    else "Priority selected using AI suggestion or MEDIUM fallback."
                )

            )

            # 6. Record initial Agent assignment
            ticket.history.create(
                action=TicketHistory.Action.ASSIGNED,
                changed_by=request.user,
                new_value=request.user.username,
                comment="Ticket initially assigned to converting agent."
            )

            # 7. Update complaint status
            complaint.status = Complaint.Status.CONVERTED
            complaint.save(
                update_fields=["status", "updated_at"]
            )

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


class TicketMessageListCreateView(APIView):

    permission_classes = [IsAuthenticated]

    def get(self, request, ticket_id):

        ticket = get_accessible_ticket(request.user, ticket_id)

        messages = ticket.messages.select_related(
            "sender",
            "ticket"
        ).all()

        serializer = TicketMessageSerializer(
            messages,
            many=True
        )

        return Response(serializer.data, status=status.HTTP_200_OK)

    def post(self, request, ticket_id):

        ticket = get_accessible_ticket(request.user, ticket_id)

        serializer = TicketMessageSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        with transaction.atomic():

            # Save the actual conversation message
            message = serializer.save(
                ticket=ticket,
                sender=request.user
            )

            profile = getattr(request.user, "profile", None)

            # Only the assigned Agent's first reply counts
            if (
                profile
                and profile.role == UserProfile.Role.AGENT
                and ticket.assigned_agent_id == request.user.id
            ):

                sla = TicketSLA.objects.select_for_update().filter(
                    ticket=ticket
                ).first()

                if sla and not sla.first_response_at:

                    first_response_time = timezone.now()

                    sla.first_response_at = first_response_time
                    sla.last_checked_at = first_response_time

                    if first_response_time <= sla.response_deadline:
                        sla.response_status = TicketSLA.Status.MET
                    else:
                        sla.response_status = TicketSLA.Status.BREACHED

                    sla.save(
                        update_fields=[
                            "first_response_at",
                            "response_status",
                            "last_checked_at",
                            "updated_at"
                        ]
                    )

                    ticket.history.create(
                        action=TicketHistory.Action.FIRST_RESPONSE_RECORDED,
                        changed_by=request.user,
                        new_value=first_response_time.isoformat(),
                        comment=(
                            "First response recorded through ticket messaging. "
                            f"SLA status: {sla.response_status}."
                        )
                    )

        return Response(
            TicketMessageSerializer(message).data,
            status=status.HTTP_201_CREATED
        )


class AIReplyGenerationView(APIView):

    permission_classes = [IsAgentOrAbove]

    def post(self, request, ticket_id):

        ticket = get_accessible_ticket(
            request.user,
            ticket_id
        )

        messages = ticket.messages.select_related(
            "sender"
        ).order_by("created_at", "id")

        try:
            suggested_reply = generate_reply(
                ticket,
                messages
            )

        except Exception:
            logger.exception(
                "AI reply generation failed for ticket %s",
                ticket.ticket_number
            )

            return Response(
                {
                    "error": "AI reply generation is currently unavailable."
                },
                status=status.HTTP_503_SERVICE_UNAVAILABLE
            )

        return Response(
            {
                "ticket_number": ticket.ticket_number,
                "suggested_reply": suggested_reply
            },
            status=status.HTTP_200_OK
        )

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

            # Recalculate SLA when ticket priority changes
            if old_priority != ticket.priority:
                sla = TicketSLA.objects.select_for_update().filter(ticket=ticket).first()
                if sla:
                    new_policy = SLAPolicy.objects.filter(
                        priority=ticket.priority, is_active=True).first()

                    if not new_policy:
                        raise ValidationError(
                            {"priority": "No active SLA policy exists for this priority."}
                        )

                    sla.policy = new_policy
                    sla.response_target_minutes = new_policy.response_time_minutes
                    sla.resolution_target_minutes = new_policy.resolution_time_minutes

                    sla.response_deadline = (
                        ticket.created_at + timedelta(minutes=new_policy.response_time_minutes))

                    sla.resolution_deadline = (
                        ticket.created_at
                        + timedelta(minutes=new_policy.resolution_time_minutes)
                    )
                    now = timezone.now()
                    sla.last_checked_at = now

                    if sla.first_response_at:
                        sla.response_status = (
                            TicketSLA.Status.MET
                            if sla.first_response_at <= sla.response_deadline
                            else TicketSLA.Status.BREACHED
                        )

                    if sla.resolved_at:
                        sla.resolution_status = (
                            TicketSLA.Status.MET
                            if sla.resolved_at <= sla.resolution_deadline
                            else TicketSLA.Status.BREACHED
                        )
                    sla.save()

            # Reset resolution SLA when a resolved/closed ticket is reopened
            if (
                    old_status in [
                        Ticket.Status.RESOLVED,
                        Ticket.Status.CLOSED
                    ]
                and ticket.status not in [
                        Ticket.Status.RESOLVED,
                        Ticket.Status.CLOSED
                ]
            ):

                sla = TicketSLA.objects.select_for_update().filter(ticket=ticket).first()

                if sla:
                    sla.resolved_at = None
                    sla.resolution_status = TicketSLA.Status.PENDING
                    sla.last_checked_at = timezone.now()

                    sla.save(
                        update_fields=[
                            "resolved_at",
                            "resolution_status",
                            "last_checked_at",
                            "updated_at"
                        ]
                    )

            # Record resolution SLA when ticket is resolved or closed
            if (
                old_status != ticket.status
                and ticket.status in [
                    Ticket.Status.RESOLVED,
                    Ticket.Status.CLOSED
                ]
            ):
                sla = TicketSLA.objects.select_for_update().filter(
                    ticket=ticket
                ).first()

                # Older tickets may not have SLA records
                if sla and not sla.resolved_at:

                    resolution_time = timezone.now()

                    sla.resolved_at = resolution_time
                    sla.last_checked_at = resolution_time

                    if resolution_time <= sla.resolution_deadline:
                        sla.resolution_status = TicketSLA.Status.MET
                    else:
                        sla.resolution_status = TicketSLA.Status.BREACHED

                    sla.save(
                        update_fields=[
                            "resolved_at",
                            "resolution_status",
                            "last_checked_at",
                            "updated_at"
                        ]
                    )

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
            ticket.save(
                update_fields=["assigned_agent", "updated_at"]
            )

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

    # 10. Assigned Agent records the first response


class FirstResponseView(APIView):

    permission_classes = [IsAuthenticated]

    def post(self, request, ticket_id):

        ticket = get_object_or_404(Ticket, pk=ticket_id)

        profile = getattr(request.user, "profile", None)

        # Only the assigned Agent can record the first response
        if (
            not profile
            or profile.role != UserProfile.Role.AGENT
            or ticket.assigned_agent_id != request.user.id
        ):
            return Response(
                {"detail": "Only the assigned Agent can record the first response."},
                status=status.HTTP_403_FORBIDDEN
            )

        with transaction.atomic():

            # Lock SLA record to prevent duplicate first responses
            sla = TicketSLA.objects.select_for_update().filter(
                ticket=ticket
            ).first()

            if not sla:
                return Response(
                    {"error": "SLA tracking record not found."},
                    status=status.HTTP_400_BAD_REQUEST
                )

            if sla.first_response_at:
                return Response(
                    {"error": "First response has already been recorded."},
                    status=status.HTTP_400_BAD_REQUEST
                )

            # Record the first response time
            first_response_time = timezone.now()

            sla.first_response_at = first_response_time
            sla.last_checked_at = first_response_time

            # Check whether response SLA was met
            if first_response_time <= sla.response_deadline:
                sla.response_status = TicketSLA.Status.MET
            else:
                sla.response_status = TicketSLA.Status.BREACHED

            sla.save(
                update_fields=[
                    "first_response_at",
                    "response_status",
                    "last_checked_at",
                    "updated_at"
                ]
            )

            # Record the action in ticket history
            ticket.history.create(
                action=TicketHistory.Action.FIRST_RESPONSE_RECORDED,
                changed_by=request.user,
                new_value=first_response_time.isoformat(),
                comment=f"First response recorded. SLA status: {sla.response_status}."
            )

        return Response(
            {
                "message": "First response recorded successfully.",
                "ticket_number": ticket.ticket_number,
                "first_response_at": sla.first_response_at,
                "response_deadline": sla.response_deadline,
                "response_status": sla.response_status
            },
            status=status.HTTP_200_OK
        )


class KnowledgeCategoryListCreateView(generics.ListCreateAPIView):

    serializer_class = KnowledgeCategorySerializer

    queryset = KnowledgeCategory.objects.all()

    def get_permissions(self):

        if self.request.method == "POST":
            return [IsAgentOrAbove()]

        return [IsAuthenticated()]


class KnowledgeArticleListCreateView(generics.ListCreateAPIView):

    serializer_class = KnowledgeArticleSerializer

    def get_queryset(self):

        user = self.request.user
        profile = getattr(user, "profile", None)

        if profile and profile.role in {
            UserProfile.Role.AGENT,
            UserProfile.Role.ADMIN,
        }:
            return KnowledgeArticle.objects.select_related(
                "category", "author"
            ).all()

        return KnowledgeArticle.objects.select_related(
            "category", "author"
        ).filter(
            status=KnowledgeArticle.Status.PUBLISHED
        )

    def get_permissions(self):

        if self.request.method == "POST":
            return [IsAgentOrAbove()]

        return [IsAuthenticated()]

    def perform_create(self, serializer):
        serializer.save(author=self.request.user)


class FAQListCreateView(generics.ListCreateAPIView):

    serializer_class = FAQSerializer

    def get_queryset(self):

        user = self.request.user
        profile = getattr(user, "profile", None)

        if profile and profile.role in {
            UserProfile.Role.AGENT,
            UserProfile.Role.ADMIN,
        }:
            return FAQ.objects.select_related(
                "category", "author"
            ).all()

        return FAQ.objects.select_related(
            "category", "author"
        ).filter(
            status=FAQ.Status.PUBLISHED
        )

    def get_permissions(self):

        if self.request.method == "POST":
            return [IsAgentOrAbove()]

        return [IsAuthenticated()]

    def perform_create(self, serializer):
        serializer.save(author=self.request.user)


class KnowledgeCategoryDetailView(generics.RetrieveUpdateDestroyAPIView):

    serializer_class = KnowledgeCategorySerializer
    queryset = KnowledgeCategory.objects.all()

    def get_permissions(self):

        if self.request.method in ["PUT", "PATCH"]:
            return [IsAgentOrAbove()]

        if self.request.method == "DELETE":
            return [IsApplicationAdmin()]

        return [IsAuthenticated()]


class KnowledgeArticleDetailView(generics.RetrieveUpdateDestroyAPIView):
    def retrieve(self, request, *args, **kwargs):
        article = self.get_object()

        article.views_count += 1
        article.save(update_fields=["views_count"])

        serializer = self.get_serializer(article)
        return Response(serializer.data)

    serializer_class = KnowledgeArticleSerializer

    def get_queryset(self):

        user = self.request.user
        profile = getattr(user, "profile", None)

        queryset = KnowledgeArticle.objects.select_related(
            "category", "author"
        )

        if profile and profile.role in {
            UserProfile.Role.AGENT,
            UserProfile.Role.ADMIN,
        }:
            return queryset

        return queryset.filter(
            status=KnowledgeArticle.Status.PUBLISHED
        )

    def get_permissions(self):

        if self.request.method in ["PUT", "PATCH"]:
            return [IsAgentOrAbove()]

        if self.request.method == "DELETE":
            return [IsApplicationAdmin()]

        return [IsAuthenticated()]


class FAQDetailView(generics.RetrieveUpdateDestroyAPIView):
    def retrieve(self, request, *args, **kwargs):
        faq = self.get_object()

        faq.views_count += 1
        faq.save(update_fields=["views_count"])

        serializer = self.get_serializer(faq)
        return Response(serializer.data)

    serializer_class = FAQSerializer

    def get_queryset(self):

        user = self.request.user
        profile = getattr(user, "profile", None)

        queryset = FAQ.objects.select_related(
            "category", "author"
        )

        if profile and profile.role in {
            UserProfile.Role.AGENT,
            UserProfile.Role.ADMIN,
        }:
            return queryset

        return queryset.filter(
            status=FAQ.Status.PUBLISHED
        )

    def get_permissions(self):

        if self.request.method in ["PUT", "PATCH"]:
            return [IsAgentOrAbove()]

        if self.request.method == "DELETE":
            return [IsApplicationAdmin()]

        return [IsAuthenticated()]


class KnowledgeArticlePublishView(generics.GenericAPIView):

    queryset = KnowledgeArticle.objects.all()
    serializer_class = KnowledgeArticleSerializer
    permission_classes = [IsApplicationAdmin]

    def post(self, request, *args, **kwargs):

        article = self.get_object()

        if article.status == KnowledgeArticle.Status.PUBLISHED:
            return Response(
                {"message": "Article is already published."},
                status=status.HTTP_400_BAD_REQUEST
            )

        article.status = KnowledgeArticle.Status.PUBLISHED
        article.published_at = timezone.now()
        article.save(update_fields=["status", "published_at", "updated_at"])

        return Response(
            {
                "message": "Article published successfully.",
                "article": self.get_serializer(article).data
            },
            status=status.HTTP_200_OK
        )


class FAQPublishView(generics.GenericAPIView):

    queryset = FAQ.objects.all()
    serializer_class = FAQSerializer
    permission_classes = [IsApplicationAdmin]

    def post(self, request, *args, **kwargs):

        faq = self.get_object()

        if faq.status == FAQ.Status.PUBLISHED:
            return Response(
                {"message": "FAQ is already published."},
                status=status.HTTP_400_BAD_REQUEST
            )

        faq.status = FAQ.Status.PUBLISHED
        faq.published_at = timezone.now()
        faq.save(update_fields=["status", "published_at", "updated_at"])

        return Response(
            {
                "message": "FAQ published successfully.",
                "faq": self.get_serializer(faq).data
            },
            status=status.HTTP_200_OK
        )
