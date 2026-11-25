
from django.contrib.auth.models import User
from django.utils import timezone
from datetime import timedelta

from rest_framework import status
from rest_framework.test import APITestCase
from unittest.mock import patch
from ticket_Api.ai_services.reply_generator import generate_reply

from accounts.models import UserProfile
from .sla_monitor import process_sla_monitoring
from .models import (
    Complaint,
    Ticket,
    TicketHistory,
    TicketSLA,
    SLAPolicy,
    TicketEscalation,
    KnowledgeCategory,
    KnowledgeArticle,
    FAQ,
    TicketMessage,
)


class ComplaintAndTicketAPITests(APITestCase):

    def create_user(self, username, role):
        user = User.objects.create_user(
            username=username,
            email=f"{username}@example.com",
            password="StrongTest@12345"
        )

        user.profile.role = role
        user.profile.save(update_fields=["role", "updated_at"])

        return user

    def create_complaint(self, customer, category="BILLING"):
        return Complaint.objects.create(
            customer=customer,
            subject="Payment issue",
            description="Payment deducted but order not confirmed.",
            category=category
        )

    def create_ticket(self, customer, agent, category="BILLING"):
        complaint = self.create_complaint(customer, category)

        return Ticket.objects.create(
            complaint=complaint,
            customer=customer,
            assigned_agent=agent,
            subject=complaint.subject,
            description=complaint.description,
            category=category
        )

    # 1. Customer can submit a complaint
    def test_customer_can_submit_complaint(self):
        customer = self.create_user(
            "customer1", UserProfile.Role.CUSTOMER
        )

        self.client.force_authenticate(user=customer)

        response = self.client.post(
            "/api/complaints/",
            {
                "subject": "Payment problem",
                "description": "Payment was deducted.",
                "category": "BILLING"
            },
            format="json"
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_201_CREATED
        )

        self.assertEqual(Complaint.objects.count(), 1)

        complaint = Complaint.objects.first()

        self.assertEqual(complaint.customer, customer)
        self.assertEqual(
            complaint.status,
            Complaint.Status.PENDING
        )

    # 2. Agent cannot submit a customer complaint
    def test_agent_cannot_submit_complaint(self):
        agent = self.create_user(
            "agent1", UserProfile.Role.AGENT
        )

        self.client.force_authenticate(user=agent)

        response = self.client.post(
            "/api/complaints/",
            {
                "subject": "Payment problem",
                "description": "Payment was deducted.",
                "category": "BILLING"
            },
            format="json"
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_403_FORBIDDEN
        )

    # 3. Customer can view only their own complaints
    def test_customer_can_view_only_own_complaints(self):
        customer1 = self.create_user(
            "customer1", UserProfile.Role.CUSTOMER
        )
        customer2 = self.create_user(
            "customer2", UserProfile.Role.CUSTOMER
        )

        complaint1 = self.create_complaint(customer1)
        self.create_complaint(customer2)

        self.client.force_authenticate(user=customer1)

        response = self.client.get("/api/complaints/my/")

        self.assertEqual(response.status_code, status.HTTP_200_OK)

        self.assertEqual(len(response.data), 1)
        self.assertEqual(
            response.data[0]["id"],
            complaint1.id
        )

    # 4. Customer cannot view pending complaints queue
    def test_customer_cannot_view_pending_complaints(self):
        customer = self.create_user(
            "customer1", UserProfile.Role.CUSTOMER
        )

        self.client.force_authenticate(user=customer)

        response = self.client.get("/api/complaints/pending/")

        self.assertEqual(
            response.status_code,
            status.HTTP_403_FORBIDDEN
        )

    # 5. Agent and Admin can view pending complaints
    def test_agent_and_admin_can_view_pending_complaints(self):
        customer = self.create_user(
            "customer1", UserProfile.Role.CUSTOMER
        )
        agent = self.create_user(
            "agent1", UserProfile.Role.AGENT
        )
        admin = self.create_user(
            "admin1", UserProfile.Role.ADMIN
        )

        complaint = self.create_complaint(customer)

        for user in [agent, admin]:
            self.client.force_authenticate(user=user)

            response = self.client.get(
                "/api/complaints/pending/"
            )

            self.assertEqual(
                response.status_code,
                status.HTTP_200_OK
            )

            self.assertEqual(
                response.data[0]["id"],
                complaint.id
            )

    # 6. Agent can convert complaint into ticket
    def test_agent_can_convert_complaint_into_ticket(self):
        customer = self.create_user(
            "customer1", UserProfile.Role.CUSTOMER
        )
        agent = self.create_user(
            "agent1", UserProfile.Role.AGENT
        )

        complaint = self.create_complaint(customer)

        self.client.force_authenticate(user=agent)

        response = self.client.post(
            f"/api/complaints/{complaint.id}/convert/",
            {"priority": "HIGH"},
            format="json"
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_201_CREATED
        )

        ticket = Ticket.objects.get(complaint=complaint)

        expected_number = (
            f"BILL-{timezone.localdate().year}-{ticket.id:06d}"
        )

        self.assertEqual(
            ticket.ticket_number,
            expected_number
        )

        self.assertEqual(ticket.customer, customer)
        self.assertEqual(ticket.assigned_agent, agent)
        self.assertEqual(ticket.priority, Ticket.Priority.HIGH)
        self.assertEqual(ticket.status, Ticket.Status.OPEN)

        complaint.refresh_from_db()

        self.assertEqual(
            complaint.status,
            Complaint.Status.CONVERTED
        )

    # 7. Admin cannot convert complaint
    def test_admin_cannot_convert_complaint(self):
        customer = self.create_user(
            "customer1", UserProfile.Role.CUSTOMER
        )
        admin = self.create_user(
            "admin1", UserProfile.Role.ADMIN
        )

        complaint = self.create_complaint(customer)

        self.client.force_authenticate(user=admin)

        response = self.client.post(
            f"/api/complaints/{complaint.id}/convert/",
            {"priority": "HIGH"},
            format="json"
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_403_FORBIDDEN
        )

        self.assertFalse(
            Ticket.objects.filter(complaint=complaint).exists()
        )

    # 8. Customer cannot convert complaint
    def test_customer_cannot_convert_complaint(self):
        customer = self.create_user(
            "customer1", UserProfile.Role.CUSTOMER
        )
        complaint = self.create_complaint(customer)

        self.client.force_authenticate(user=customer)

        response = self.client.post(
            f"/api/complaints/{complaint.id}/convert/",
            {"priority": "HIGH"},
            format="json"
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_403_FORBIDDEN
        )

    # 9. Same complaint cannot be converted twice
    def test_complaint_cannot_be_converted_twice(self):
        customer = self.create_user(
            "customer1", UserProfile.Role.CUSTOMER
        )
        agent = self.create_user(
            "agent1", UserProfile.Role.AGENT
        )

        complaint = self.create_complaint(customer)

        self.client.force_authenticate(user=agent)

        first_response = self.client.post(
            f"/api/complaints/{complaint.id}/convert/",
            {"priority": "MEDIUM"},
            format="json"
        )

        second_response = self.client.post(
            f"/api/complaints/{complaint.id}/convert/",
            {"priority": "HIGH"},
            format="json"
        )

        self.assertEqual(
            first_response.status_code,
            status.HTTP_201_CREATED
        )

        self.assertEqual(
            second_response.status_code,
            status.HTTP_400_BAD_REQUEST
        )

        self.assertEqual(Ticket.objects.count(), 1)

    # 10. Invalid ticket priority is rejected
    def test_invalid_ticket_priority_is_rejected(self):
        customer = self.create_user(
            "customer1", UserProfile.Role.CUSTOMER
        )
        agent = self.create_user(
            "agent1", UserProfile.Role.AGENT
        )

        complaint = self.create_complaint(customer)

        self.client.force_authenticate(user=agent)

        response = self.client.post(
            f"/api/complaints/{complaint.id}/convert/",
            {"priority": "URGENT"},
            format="json"
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_400_BAD_REQUEST
        )

        self.assertEqual(Ticket.objects.count(), 0)

    # 11. Customer sees only their own tickets
    def test_customer_sees_only_own_tickets(self):
        customer1 = self.create_user(
            "customer1", UserProfile.Role.CUSTOMER
        )
        customer2 = self.create_user(
            "customer2", UserProfile.Role.CUSTOMER
        )
        agent = self.create_user(
            "agent1", UserProfile.Role.AGENT
        )

        ticket1 = self.create_ticket(customer1, agent)
        self.create_ticket(customer2, agent)

        self.client.force_authenticate(user=customer1)

        response = self.client.get("/api/tickets/")

        self.assertEqual(response.status_code, status.HTTP_200_OK)

        self.assertEqual(len(response.data), 1)
        self.assertEqual(
            response.data[0]["id"],
            ticket1.id
        )

    # 12. Agent sees only assigned tickets
    def test_agent_sees_only_assigned_tickets(self):
        customer = self.create_user(
            "customer1", UserProfile.Role.CUSTOMER
        )
        agent1 = self.create_user(
            "agent1", UserProfile.Role.AGENT
        )
        agent2 = self.create_user(
            "agent2", UserProfile.Role.AGENT
        )

        ticket1 = self.create_ticket(customer, agent1)
        self.create_ticket(customer, agent2)

        self.client.force_authenticate(user=agent1)

        response = self.client.get("/api/tickets/")

        self.assertEqual(response.status_code, status.HTTP_200_OK)

        self.assertEqual(len(response.data), 1)
        self.assertEqual(
            response.data[0]["id"],
            ticket1.id
        )

    # 13. Admin can view all tickets
    def test_admin_can_view_all_tickets(self):
        customer1 = self.create_user(
            "customer1", UserProfile.Role.CUSTOMER
        )
        customer2 = self.create_user(
            "customer2", UserProfile.Role.CUSTOMER
        )
        agent = self.create_user(
            "agent1", UserProfile.Role.AGENT
        )
        admin = self.create_user(
            "admin1", UserProfile.Role.ADMIN
        )

        self.create_ticket(customer1, agent)
        self.create_ticket(customer2, agent)

        self.client.force_authenticate(user=admin)

        response = self.client.get("/api/tickets/")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data), 2)

    # 14. Generated ticket numbers are unique
    def test_ticket_numbers_are_unique(self):
        customer = self.create_user(
            "customer1", UserProfile.Role.CUSTOMER
        )
        agent = self.create_user(
            "agent1", UserProfile.Role.AGENT
        )

        ticket1 = self.create_ticket(
            customer, agent, category="BILLING"
        )
        ticket2 = self.create_ticket(
            customer, agent, category="ACCOUNT"
        )

        self.assertNotEqual(
            ticket1.ticket_number,
            ticket2.ticket_number
        )

        self.assertTrue(
            ticket1.ticket_number.startswith("BILL-")
        )
        self.assertTrue(
            ticket2.ticket_number.startswith("ACCT-")
        )

    # 15. Customer can view own ticket details only
    def test_customer_ticket_detail_access(self):
        customer1 = self.create_user("customer3", UserProfile.Role.CUSTOMER)
        customer2 = self.create_user("customer4", UserProfile.Role.CUSTOMER)
        agent = self.create_user("agent3", UserProfile.Role.AGENT)

        ticket = self.create_ticket(customer1, agent)
        other_ticket = self.create_ticket(customer2, agent)

        self.client.force_authenticate(user=customer1)

        response = self.client.get(f"/api/tickets/{ticket.id}/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        response = self.client.get(f"/api/tickets/{other_ticket.id}/")
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    # 16. Assigned Agent and Admin can view ticket details
    def test_agent_and_admin_can_view_ticket_details(self):
        customer = self.create_user("customer5", UserProfile.Role.CUSTOMER)
        agent = self.create_user("agent4", UserProfile.Role.AGENT)
        admin = self.create_user("admin2", UserProfile.Role.ADMIN)

        ticket = self.create_ticket(customer, agent)

        for user in [agent, admin]:
            self.client.force_authenticate(user=user)

            response = self.client.get(f"/api/tickets/{ticket.id}/")

            self.assertEqual(response.status_code, status.HTTP_200_OK)
            self.assertEqual(response.data["id"], ticket.id)

    # 17. Assigned Agent can update ticket status and priority
    def test_assigned_agent_can_update_ticket(self):
        customer = self.create_user("customer6", UserProfile.Role.CUSTOMER)
        agent = self.create_user("agent5", UserProfile.Role.AGENT)

        ticket = self.create_ticket(customer, agent)

        self.client.force_authenticate(user=agent)

        response = self.client.patch(
            f"/api/tickets/{ticket.id}/update/",
            {"status": "IN_PROGRESS", "priority": "HIGH"},
            format="json"
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)

        ticket.refresh_from_db()

        self.assertEqual(ticket.status, Ticket.Status.IN_PROGRESS)
        self.assertEqual(ticket.priority, Ticket.Priority.HIGH)

        self.assertEqual(
            TicketHistory.objects.filter(ticket=ticket).count(), 2
        )

    # 18. Agent cannot update another Agent's ticket
    def test_agent_cannot_update_unassigned_ticket(self):
        customer = self.create_user("customer7", UserProfile.Role.CUSTOMER)
        agent1 = self.create_user("agent6", UserProfile.Role.AGENT)
        agent2 = self.create_user("agent7", UserProfile.Role.AGENT)

        ticket = self.create_ticket(customer, agent1)

        self.client.force_authenticate(user=agent2)

        response = self.client.patch(
            f"/api/tickets/{ticket.id}/update/",
            {"status": "IN_PROGRESS"},
            format="json"
        )

        self.assertEqual(
            response.status_code, status.HTTP_403_FORBIDDEN
        )

        ticket.refresh_from_db()
        self.assertEqual(ticket.status, Ticket.Status.OPEN)

    # 19. Customer cannot update ticket status or priority
    def test_customer_cannot_update_ticket(self):
        customer = self.create_user("customer8", UserProfile.Role.CUSTOMER)
        agent = self.create_user("agent8", UserProfile.Role.AGENT)

        ticket = self.create_ticket(customer, agent)

        self.client.force_authenticate(user=customer)

        response = self.client.patch(
            f"/api/tickets/{ticket.id}/update/",
            {"status": "RESOLVED"},
            format="json"
        )

        self.assertEqual(
            response.status_code, status.HTTP_403_FORBIDDEN
        )

    # 20. Admin can update ticket status and priority
    def test_admin_can_update_ticket(self):
        customer = self.create_user("customer9", UserProfile.Role.CUSTOMER)
        agent = self.create_user("agent9", UserProfile.Role.AGENT)
        admin = self.create_user("admin3", UserProfile.Role.ADMIN)

        ticket = self.create_ticket(customer, agent)

        self.client.force_authenticate(user=admin)

        response = self.client.patch(
            f"/api/tickets/{ticket.id}/update/",
            {"status": "RESOLVED", "priority": "CRITICAL"},
            format="json"
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)

        ticket.refresh_from_db()

        self.assertEqual(ticket.status, Ticket.Status.RESOLVED)
        self.assertEqual(ticket.priority, Ticket.Priority.CRITICAL)

    # 21. Admin can reassign a ticket to another Agent
    def test_admin_can_reassign_ticket(self):
        customer = self.create_user("customer10", UserProfile.Role.CUSTOMER)
        agent1 = self.create_user("agent10", UserProfile.Role.AGENT)
        agent2 = self.create_user("agent11", UserProfile.Role.AGENT)
        admin = self.create_user("admin4", UserProfile.Role.ADMIN)

        ticket = self.create_ticket(customer, agent1)

        self.client.force_authenticate(user=admin)

        response = self.client.patch(
            f"/api/tickets/{ticket.id}/assign/",
            {"agent_id": agent2.id},
            format="json"
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)

        ticket.refresh_from_db()

        self.assertEqual(ticket.assigned_agent, agent2)

        history = TicketHistory.objects.get(ticket=ticket)

        self.assertEqual(
            history.action, TicketHistory.Action.REASSIGNED
        )
        self.assertEqual(history.old_value, agent1.username)
        self.assertEqual(history.new_value, agent2.username)

    # 22. Non-admin users cannot assign or reassign tickets
    def test_agent_cannot_reassign_ticket(self):
        customer = self.create_user("customer11", UserProfile.Role.CUSTOMER)
        agent1 = self.create_user("agent12", UserProfile.Role.AGENT)
        agent2 = self.create_user("agent13", UserProfile.Role.AGENT)

        ticket = self.create_ticket(customer, agent1)

        self.client.force_authenticate(user=agent1)

        response = self.client.patch(
            f"/api/tickets/{ticket.id}/assign/",
            {"agent_id": agent2.id},
            format="json"
        )

        self.assertEqual(
            response.status_code, status.HTTP_403_FORBIDDEN
        )

    # 23. Admin cannot assign a ticket to a Customer
    def test_admin_cannot_assign_ticket_to_customer(self):
        customer1 = self.create_user("customer12", UserProfile.Role.CUSTOMER)
        customer2 = self.create_user("customer13", UserProfile.Role.CUSTOMER)
        agent = self.create_user("agent14", UserProfile.Role.AGENT)
        admin = self.create_user("admin5", UserProfile.Role.ADMIN)

        ticket = self.create_ticket(customer1, agent)

        self.client.force_authenticate(user=admin)

        response = self.client.patch(
            f"/api/tickets/{ticket.id}/assign/",
            {"agent_id": customer2.id},
            format="json"
        )

        self.assertEqual(
            response.status_code, status.HTTP_400_BAD_REQUEST
        )

    # 24. Users with access can view ticket history
    def test_ticket_history_access_and_tracking(self):
        customer = self.create_user("customer14", UserProfile.Role.CUSTOMER)
        other_customer = self.create_user(
            "customer15", UserProfile.Role.CUSTOMER)
        agent = self.create_user("agent15", UserProfile.Role.AGENT)
        other_agent = self.create_user("agent16", UserProfile.Role.AGENT)
        admin = self.create_user("admin6", UserProfile.Role.ADMIN)

        ticket = self.create_ticket(customer, agent)

        # Generate history by updating the ticket.
        self.client.force_authenticate(user=agent)

        self.client.patch(
            f"/api/tickets/{ticket.id}/update/",
            {"status": "IN_PROGRESS"},
            format="json"
        )

        # Customer, assigned Agent and Admin can view history.
        for user in [customer, agent, admin]:
            self.client.force_authenticate(user=user)

            response = self.client.get(
                f"/api/tickets/{ticket.id}/history/"
            )

            self.assertEqual(response.status_code, status.HTTP_200_OK)
            self.assertEqual(len(response.data), 1)
            self.assertEqual(
                response.data[0]["action"],
                TicketHistory.Action.STATUS_CHANGED
            )

        # Other Customer and unassigned Agent cannot view history.
        for user in [other_customer, other_agent]:
            self.client.force_authenticate(user=user)

            response = self.client.get(
                f"/api/tickets/{ticket.id}/history/"
            )

            self.assertEqual(
                response.status_code, status.HTTP_403_FORBIDDEN
            )

    # 25. Ticket conversion automatically creates SLA deadlines

    def test_ticket_conversion_creates_sla(self):

        customer = self.create_user(
            "sla_customer",
            UserProfile.Role.CUSTOMER
        )

        agent = self.create_user(
            "sla_agent",
            UserProfile.Role.AGENT
        )

        complaint = self.create_complaint(customer)

        self.client.force_authenticate(user=agent)

        response = self.client.post(
            f"/api/complaints/{complaint.id}/convert/",
            {"priority": "HIGH"},
            format="json"
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_201_CREATED
        )

        ticket = Ticket.objects.get(complaint=complaint)

        sla = TicketSLA.objects.get(ticket=ticket)

        # Verify SLA policy
        self.assertEqual(sla.policy.priority, "HIGH")

        # Verify response and resolution targets
        self.assertEqual(sla.response_target_minutes, 60)
        self.assertEqual(sla.resolution_target_minutes, 480)

        # Verify calculated deadlines
        self.assertEqual(
            sla.response_deadline,
            ticket.created_at + timezone.timedelta(minutes=60)
        )

        self.assertEqual(
            sla.resolution_deadline,
            ticket.created_at + timezone.timedelta(minutes=480)
        )

        # Verify initial SLA statuses
        self.assertEqual(
            sla.response_status,
            TicketSLA.Status.PENDING
        )

        self.assertEqual(
            sla.resolution_status,
            TicketSLA.Status.PENDING
        )

    def create_sla_for_ticket(self, ticket, response_deadline=None):

        policy = SLAPolicy.objects.get(
            priority=ticket.priority
        )

        now = timezone.now()

        return TicketSLA.objects.create(
            ticket=ticket,
            policy=policy,
            response_target_minutes=policy.response_time_minutes,
            resolution_target_minutes=policy.resolution_time_minutes,
            response_deadline=(
                response_deadline or now + timedelta(hours=1)
            ),
            resolution_deadline=now + timedelta(hours=8)
        )

    # 26. Assigned Agent can record first response within SLA
    def test_agent_can_record_first_response_within_sla(self):

        customer = self.create_user(
            "response_customer",
            UserProfile.Role.CUSTOMER
        )

        agent = self.create_user(
            "response_agent",
            UserProfile.Role.AGENT
        )

        ticket = self.create_ticket(customer, agent)
        self.create_sla_for_ticket(ticket)

        self.client.force_authenticate(user=agent)

        response = self.client.post(
            f"/api/tickets/{ticket.id}/first-response/",
            {},
            format="json"
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_200_OK
        )

        sla = TicketSLA.objects.get(ticket=ticket)

        self.assertIsNotNone(sla.first_response_at)

        self.assertEqual(
            sla.response_status,
            TicketSLA.Status.MET
        )

        self.assertTrue(
            TicketHistory.objects.filter(
                ticket=ticket,
                action=TicketHistory.Action.FIRST_RESPONSE_RECORDED,
                changed_by=agent
            ).exists()
        )

    # 27. First response after deadline breaches response SLA
    def test_first_response_after_deadline_is_breached(self):

        customer = self.create_user(
            "late_customer",
            UserProfile.Role.CUSTOMER
        )

        agent = self.create_user(
            "late_agent",
            UserProfile.Role.AGENT
        )

        ticket = self.create_ticket(customer, agent)

        past_deadline = timezone.now() - timedelta(minutes=5)

        self.create_sla_for_ticket(
            ticket,
            response_deadline=past_deadline
        )

        self.client.force_authenticate(user=agent)

        response = self.client.post(
            f"/api/tickets/{ticket.id}/first-response/",
            {},
            format="json"
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_200_OK
        )

        sla = TicketSLA.objects.get(ticket=ticket)

        self.assertEqual(
            sla.response_status,
            TicketSLA.Status.BREACHED
        )

    # 28. Customer cannot record first response
    def test_customer_cannot_record_first_response(self):

        customer = self.create_user(
            "response_customer2",
            UserProfile.Role.CUSTOMER
        )

        agent = self.create_user(
            "response_agent2",
            UserProfile.Role.AGENT
        )

        ticket = self.create_ticket(customer, agent)
        self.create_sla_for_ticket(ticket)

        self.client.force_authenticate(user=customer)

        response = self.client.post(
            f"/api/tickets/{ticket.id}/first-response/",
            {},
            format="json"
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_403_FORBIDDEN
        )

        sla = TicketSLA.objects.get(ticket=ticket)

        self.assertIsNone(sla.first_response_at)

    # 29. Unassigned Agent cannot record first response
    def test_unassigned_agent_cannot_record_first_response(self):

        customer = self.create_user(
            "response_customer3",
            UserProfile.Role.CUSTOMER
        )

        assigned_agent = self.create_user(
            "assigned_agent3",
            UserProfile.Role.AGENT
        )

        other_agent = self.create_user(
            "other_agent3",
            UserProfile.Role.AGENT
        )

        ticket = self.create_ticket(customer, assigned_agent)
        self.create_sla_for_ticket(ticket)

        self.client.force_authenticate(user=other_agent)

        response = self.client.post(
            f"/api/tickets/{ticket.id}/first-response/",
            {},
            format="json"
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_403_FORBIDDEN
        )

    # 30. First response cannot be recorded twice
    def test_first_response_cannot_be_recorded_twice(self):

        customer = self.create_user(
            "response_customer4",
            UserProfile.Role.CUSTOMER
        )

        agent = self.create_user(
            "response_agent4",
            UserProfile.Role.AGENT
        )

        ticket = self.create_ticket(customer, agent)
        self.create_sla_for_ticket(ticket)

        self.client.force_authenticate(user=agent)

        first_response = self.client.post(
            f"/api/tickets/{ticket.id}/first-response/",
            {},
            format="json"
        )

        second_response = self.client.post(
            f"/api/tickets/{ticket.id}/first-response/",
            {},
            format="json"
        )

        self.assertEqual(
            first_response.status_code,
            status.HTTP_200_OK
        )

        self.assertEqual(
            second_response.status_code,
            status.HTTP_400_BAD_REQUEST
        )

        self.assertEqual(
            TicketHistory.objects.filter(
                ticket=ticket,
                action=TicketHistory.Action.FIRST_RESPONSE_RECORDED
            ).count(),
            1
        )

    # 31. Agent resolves ticket within the resolution SLA

    def test_agent_resolves_ticket_within_sla(self):

        customer = self.create_user(
            "resolve_customer",
            UserProfile.Role.CUSTOMER
        )

        agent = self.create_user(
            "resolve_agent",
            UserProfile.Role.AGENT
        )

        ticket = self.create_ticket(customer, agent)
        sla = self.create_sla_for_ticket(ticket)

        self.client.force_authenticate(user=agent)

        response = self.client.patch(
            f"/api/tickets/{ticket.id}/update/",
            {"status": "RESOLVED"},
            format="json"
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_200_OK
        )

        sla.refresh_from_db()

        self.assertIsNotNone(sla.resolved_at)

        self.assertEqual(
            sla.resolution_status,
            TicketSLA.Status.MET
        )

    # 32. Agent resolves ticket after the resolution deadline
    def test_agent_resolves_ticket_after_sla_deadline(self):

        customer = self.create_user(
            "late_resolve_customer",
            UserProfile.Role.CUSTOMER
        )

        agent = self.create_user(
            "late_resolve_agent",
            UserProfile.Role.AGENT
        )

        ticket = self.create_ticket(customer, agent)

        sla = self.create_sla_for_ticket(ticket)

        sla.resolution_deadline = (
            timezone.now() - timedelta(minutes=5)
        )
        sla.save(update_fields=["resolution_deadline"])

        self.client.force_authenticate(user=agent)

        response = self.client.patch(
            f"/api/tickets/{ticket.id}/update/",
            {"status": "RESOLVED"},
            format="json"
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_200_OK
        )

        sla.refresh_from_db()

        self.assertEqual(
            sla.resolution_status,
            TicketSLA.Status.BREACHED
        )

    # 33. Closing a ticket records resolution SLA
    def test_closing_ticket_records_resolution_sla(self):

        customer = self.create_user(
            "close_customer",
            UserProfile.Role.CUSTOMER
        )

        agent = self.create_user(
            "close_agent",
            UserProfile.Role.AGENT
        )

        ticket = self.create_ticket(customer, agent)
        sla = self.create_sla_for_ticket(ticket)

        self.client.force_authenticate(user=agent)

        response = self.client.patch(
            f"/api/tickets/{ticket.id}/update/",
            {"status": "CLOSED"},
            format="json"
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_200_OK
        )

        sla.refresh_from_db()

        self.assertIsNotNone(sla.resolved_at)

        self.assertEqual(
            sla.resolution_status,
            TicketSLA.Status.MET
        )

    # 34. Resolution timestamp is not overwritten when ticket is closed
    def test_resolution_timestamp_is_preserved(self):

        customer = self.create_user(
            "timestamp_customer",
            UserProfile.Role.CUSTOMER
        )

        agent = self.create_user(
            "timestamp_agent",
            UserProfile.Role.AGENT
        )

        ticket = self.create_ticket(customer, agent)
        sla = self.create_sla_for_ticket(ticket)

        self.client.force_authenticate(user=agent)

        # First resolve the ticket
        self.client.patch(
            f"/api/tickets/{ticket.id}/update/",
            {"status": "RESOLVED"},
            format="json"
        )

        sla.refresh_from_db()
        original_timestamp = sla.resolved_at

        # Then close the ticket
        response = self.client.patch(
            f"/api/tickets/{ticket.id}/update/",
            {"status": "CLOSED"},
            format="json"
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_200_OK
        )

        sla.refresh_from_db()

        self.assertEqual(
            sla.resolved_at,
            original_timestamp
        )

    # 35. Monitoring detects response and resolution SLA breaches

    def test_monitor_detects_sla_breaches_and_creates_escalations(self):

        customer = self.create_user(
            "monitor_customer",
            UserProfile.Role.CUSTOMER
        )

        agent = self.create_user(
            "monitor_agent",
            UserProfile.Role.AGENT
        )

        ticket = self.create_ticket(customer, agent)
        sla = self.create_sla_for_ticket(ticket)

        now = timezone.now()
        past_deadline = now - timedelta(minutes=75)

        sla.response_deadline = past_deadline
        sla.resolution_deadline = past_deadline
        sla.save(
            update_fields=[
                "response_deadline",
                "resolution_deadline"
            ]
        )

        results = process_sla_monitoring(now=now)

        sla.refresh_from_db()

        self.assertEqual(
            sla.response_status,
            TicketSLA.Status.BREACHED
        )

        self.assertEqual(
            sla.resolution_status,
            TicketSLA.Status.BREACHED
        )

        self.assertEqual(results["response_breaches"], 1)
        self.assertEqual(results["resolution_breaches"], 1)
        self.assertEqual(results["escalations_created"], 6)

        self.assertEqual(
            TicketEscalation.objects.filter(ticket=ticket).count(),
            6
        )

    # 36. Repeated monitoring must not create duplicate escalations
    def test_monitor_does_not_create_duplicate_escalations(self):

        customer = self.create_user(
            "duplicate_monitor_customer",
            UserProfile.Role.CUSTOMER
        )

        agent = self.create_user(
            "duplicate_monitor_agent",
            UserProfile.Role.AGENT
        )

        ticket = self.create_ticket(customer, agent)
        sla = self.create_sla_for_ticket(ticket)

        now = timezone.now()
        past_deadline = now - timedelta(minutes=75)

        sla.response_deadline = past_deadline
        sla.resolution_deadline = past_deadline
        sla.save(
            update_fields=[
                "response_deadline",
                "resolution_deadline"
            ]
        )

        first_run = process_sla_monitoring(now=now)
        second_run = process_sla_monitoring(now=now)

        self.assertEqual(
            first_run["escalations_created"], 6
        )

        self.assertEqual(
            second_run["escalations_created"], 0
        )

        self.assertEqual(
            TicketEscalation.objects.filter(ticket=ticket).count(),
            6
        )

    # 37. Monitoring does not escalate tickets within SLA
    def test_monitor_does_not_escalate_tickets_within_sla(self):

        customer = self.create_user(
            "safe_monitor_customer",
            UserProfile.Role.CUSTOMER
        )

        agent = self.create_user(
            "safe_monitor_agent",
            UserProfile.Role.AGENT
        )

        ticket = self.create_ticket(customer, agent)
        sla = self.create_sla_for_ticket(ticket)

        now = timezone.now()

        results = process_sla_monitoring(now=now)

        sla.refresh_from_db()

        self.assertEqual(
            sla.response_status,
            TicketSLA.Status.PENDING
        )

        self.assertEqual(
            sla.resolution_status,
            TicketSLA.Status.PENDING
        )

        self.assertEqual(results["escalations_created"], 0)

        self.assertEqual(
            TicketEscalation.objects.filter(ticket=ticket).count(),
            0
        )

        # 38. Reopening a resolved ticket resets resolution SLA

    def test_reopening_resolved_ticket_resets_resolution_sla(self):

        customer = self.create_user(
            "reopen_customer",
            UserProfile.Role.CUSTOMER
        )

        agent = self.create_user(
            "reopen_agent",
            UserProfile.Role.AGENT
        )

        ticket = self.create_ticket(customer, agent)
        sla = self.create_sla_for_ticket(ticket)

        self.client.force_authenticate(user=agent)

        # First resolve the ticket
        response = self.client.patch(
            f"/api/tickets/{ticket.id}/update/",
            {"status": "RESOLVED"},
            format="json"
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)

        sla.refresh_from_db()
        self.assertIsNotNone(sla.resolved_at)

        # Reopen the ticket
        response = self.client.patch(
            f"/api/tickets/{ticket.id}/update/",
            {"status": "IN_PROGRESS"},
            format="json"
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)

        sla.refresh_from_db()

        self.assertIsNone(sla.resolved_at)
        self.assertEqual(
            sla.resolution_status,
            TicketSLA.Status.PENDING
        )

    # 39. Changing ticket priority recalculates SLA deadlines

    def test_priority_change_recalculates_sla(self):

        customer = self.create_user(
            "priority_customer",
            UserProfile.Role.CUSTOMER
        )

        agent = self.create_user(
            "priority_agent",
            UserProfile.Role.AGENT
        )

        ticket = self.create_ticket(customer, agent)
        sla = self.create_sla_for_ticket(ticket)

        # Select another active SLA policy
        new_policy = SLAPolicy.objects.filter(
            is_active=True
        ).exclude(
            priority=ticket.priority
        ).first()

        self.assertIsNotNone(new_policy)

        self.client.force_authenticate(user=agent)

        response = self.client.patch(
            f"/api/tickets/{ticket.id}/update/",
            {"priority": new_policy.priority},
            format="json"
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_200_OK
        )

        sla.refresh_from_db()
        ticket.refresh_from_db()

        self.assertEqual(ticket.priority, new_policy.priority)

        # Verify the new SLA policy
        self.assertEqual(sla.policy, new_policy)

        # Verify updated target durations
        self.assertEqual(
            sla.response_target_minutes,
            new_policy.response_time_minutes
        )

        self.assertEqual(
            sla.resolution_target_minutes,
            new_policy.resolution_time_minutes
        )

        # Verify recalculated deadlines
        self.assertEqual(
            sla.response_deadline,
            ticket.created_at + timedelta(
                minutes=new_policy.response_time_minutes
            )
        )

        self.assertEqual(
            sla.resolution_deadline,
            ticket.created_at + timedelta(
                minutes=new_policy.resolution_time_minutes
            )
        )

    # 40. Priority change is rejected when no active SLA policy exists

    def test_priority_change_rejected_without_active_sla_policy(self):

        customer = self.create_user(
            "inactive_policy_customer",
            UserProfile.Role.CUSTOMER
        )

        agent = self.create_user(
            "inactive_policy_agent",
            UserProfile.Role.AGENT
        )

        ticket = self.create_ticket(customer, agent)
        sla = self.create_sla_for_ticket(ticket)

        original_priority = ticket.priority
        original_policy = sla.policy

        # Deactivate all policies for other priorities
        SLAPolicy.objects.exclude(
            priority=original_priority
        ).update(is_active=False)

        self.client.force_authenticate(user=agent)

        response = self.client.patch(
            f"/api/tickets/{ticket.id}/update/",
            {"priority": "CRITICAL"},
            format="json"
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_400_BAD_REQUEST
        )

        ticket.refresh_from_db()
        sla.refresh_from_db()

        # Verify transaction rollback
        self.assertEqual(ticket.priority, original_priority)
        self.assertEqual(sla.policy, original_policy)

        # 41. Agent and Admin can create Knowledge Categories

    def test_agent_and_admin_can_create_knowledge_category(self):

        agent = self.create_user(
            "knowledge_agent",
            UserProfile.Role.AGENT
        )

        admin = self.create_user(
            "knowledge_admin",
            UserProfile.Role.ADMIN
        )

        for user in [agent, admin]:

            self.client.force_authenticate(user=user)

            response = self.client.post(
                "/api/knowledge/categories/",
                {
                    "name": f"Category {user.username}",
                    "description": "Knowledge Base category"
                },
                format="json"
            )

            self.assertEqual(
                response.status_code,
                status.HTTP_201_CREATED
            )

        self.assertEqual(KnowledgeCategory.objects.count(), 2)
        # 42. Customer cannot create Knowledge Categories

    def test_customer_cannot_create_knowledge_category(self):

        customer = self.create_user(
            "knowledge_customer",
            UserProfile.Role.CUSTOMER
        )

        self.client.force_authenticate(user=customer)

        response = self.client.post(
            "/api/knowledge/categories/",
            {
                "name": "Customer Category",
                "description": "Should not be created"
            },
            format="json"
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_403_FORBIDDEN
        )

        self.assertEqual(KnowledgeCategory.objects.count(), 0)

        # 43. Agent and Admin can create Knowledge Articles

    def test_agent_and_admin_can_create_knowledge_article(self):

        agent = self.create_user(
            "article_agent",
            UserProfile.Role.AGENT
        )

        admin = self.create_user(
            "article_admin",
            UserProfile.Role.ADMIN
        )

        category = KnowledgeCategory.objects.create(
            name="Technical Support",
            description="Technical troubleshooting articles"
        )

        for user in [agent, admin]:

            self.client.force_authenticate(user=user)

            response = self.client.post(
                "/api/knowledge/articles/",
                {
                    "title": f"Article by {user.username}",
                    "content": "Steps to troubleshoot a technical issue.",
                    "category": category.id
                },
                format="json"
            )

            self.assertEqual(
                response.status_code,
                status.HTTP_201_CREATED
            )

            article = KnowledgeArticle.objects.get(
                title=f"Article by {user.username}"
            )

            self.assertEqual(article.author, user)
            self.assertEqual(
                article.status,
                KnowledgeArticle.Status.DRAFT
            )

        self.assertEqual(KnowledgeArticle.objects.count(), 2)
        # 44. Customer cannot create Knowledge Articles

    def test_customer_cannot_create_knowledge_article(self):

        customer = self.create_user(
            "article_customer",
            UserProfile.Role.CUSTOMER
        )

        category = KnowledgeCategory.objects.create(
            name="Customer Help",
            description="Customer help articles"
        )

        self.client.force_authenticate(user=customer)

        response = self.client.post(
            "/api/knowledge/articles/",
            {
                "title": "Customer Article",
                "content": "This should not be created.",
                "category": category.id
            },
            format="json"
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_403_FORBIDDEN
        )

        self.assertEqual(KnowledgeArticle.objects.count(), 0)
        # 45. Customers can see only published Knowledge Articles

    def test_customer_sees_only_published_knowledge_articles(self):

        customer = self.create_user(
            "article_view_customer",
            UserProfile.Role.CUSTOMER
        )

        category = KnowledgeCategory.objects.create(
            name="General Help",
            description="General help articles"
        )

        agent = self.create_user(
            "article_view_agent",
            UserProfile.Role.AGENT
        )

        KnowledgeArticle.objects.create(
            title="Published Article",
            content="This article is available to customers.",
            category=category,
            author=agent,
            status=KnowledgeArticle.Status.PUBLISHED,
            published_at=timezone.now()
        )

        KnowledgeArticle.objects.create(
            title="Draft Article",
            content="This article is not yet published.",
            category=category,
            author=agent,
            status=KnowledgeArticle.Status.DRAFT
        )

        self.client.force_authenticate(user=customer)

        response = self.client.get("/api/knowledge/articles/")

        self.assertEqual(response.status_code, status.HTTP_200_OK)

        titles = [article["title"] for article in response.data]

        self.assertIn("Published Article", titles)
        self.assertNotIn("Draft Article", titles)
        self.assertEqual(len(titles), 1)
        # 46. Agents and Admins can see all Knowledge Articles

    def test_agent_and_admin_see_all_knowledge_articles(self):

        agent = self.create_user(
            "article_all_agent",
            UserProfile.Role.AGENT
        )

        admin = self.create_user(
            "article_all_admin",
            UserProfile.Role.ADMIN
        )

        category = KnowledgeCategory.objects.create(
            name="Account Help",
            description="Account-related articles"
        )

        KnowledgeArticle.objects.create(
            title="Published Account Article",
            content="Published content.",
            category=category,
            author=admin,
            status=KnowledgeArticle.Status.PUBLISHED,
            published_at=timezone.now()
        )

        KnowledgeArticle.objects.create(
            title="Draft Account Article",
            content="Draft content.",
            category=category,
            author=admin,
            status=KnowledgeArticle.Status.DRAFT
        )

        for user in [agent, admin]:

            self.client.force_authenticate(user=user)

            response = self.client.get("/api/knowledge/articles/")

            self.assertEqual(response.status_code, status.HTTP_200_OK)

            titles = [article["title"] for article in response.data]

            self.assertIn("Published Account Article", titles)
            self.assertIn("Draft Account Article", titles)
            self.assertEqual(len(titles), 2)
        # 47. Customer cannot access a Draft Knowledge Article

    def test_customer_cannot_access_draft_knowledge_article(self):

        customer = self.create_user(
            "article_draft_customer",
            UserProfile.Role.CUSTOMER
        )

        agent = self.create_user(
            "article_draft_agent",
            UserProfile.Role.AGENT
        )

        category = KnowledgeCategory.objects.create(
            name="Private Help",
            description="Unpublished help articles"
        )

        article = KnowledgeArticle.objects.create(
            title="Private Draft Article",
            content="This content must remain private.",
            category=category,
            author=agent,
            status=KnowledgeArticle.Status.DRAFT
        )

        self.client.force_authenticate(user=customer)

        response = self.client.get(
            f"/api/knowledge/articles/{article.id}/"
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_404_NOT_FOUND
        )
        # 48. Agents and Admins can access Draft Knowledge Articles

    def test_agent_and_admin_can_access_draft_knowledge_article(self):

        agent = self.create_user(
            "article_detail_agent",
            UserProfile.Role.AGENT
        )

        admin = self.create_user(
            "article_detail_admin",
            UserProfile.Role.ADMIN
        )

        category = KnowledgeCategory.objects.create(
            name="Internal Support",
            description="Internal support articles"
        )

        article = KnowledgeArticle.objects.create(
            title="Internal Draft Article",
            content="Draft content for support staff.",
            category=category,
            author=admin,
            status=KnowledgeArticle.Status.DRAFT
        )

        for user in [agent, admin]:

            self.client.force_authenticate(user=user)

            response = self.client.get(
                f"/api/knowledge/articles/{article.id}/"
            )

            self.assertEqual(
                response.status_code,
                status.HTTP_200_OK
            )

            self.assertEqual(
                response.data["title"],
                "Internal Draft Article"
            )
        # 49. Agent and Admin can edit Knowledge Articles

    def test_agent_and_admin_can_edit_knowledge_article(self):

        agent = self.create_user(
            "article_edit_agent",
            UserProfile.Role.AGENT
        )

        admin = self.create_user(
            "article_edit_admin",
            UserProfile.Role.ADMIN
        )

        category = KnowledgeCategory.objects.create(
            name="Editing Help",
            description="Article editing tests"
        )

        article = KnowledgeArticle.objects.create(
            title="Original Article",
            content="Original content.",
            category=category,
            author=admin,
            status=KnowledgeArticle.Status.DRAFT
        )

        for user in [agent, admin]:

            self.client.force_authenticate(user=user)

            response = self.client.patch(
                f"/api/knowledge/articles/{article.id}/",
                {
                    "title": f"Updated by {user.username}"
                },
                format="json"
            )

            self.assertEqual(
                response.status_code,
                status.HTTP_200_OK
            )

            article.refresh_from_db()

            self.assertEqual(
                article.title,
                f"Updated by {user.username}"
            )
        # 50. Customer cannot edit Knowledge Articles

    def test_customer_cannot_edit_knowledge_article(self):

        customer = self.create_user(
            "article_edit_customer",
            UserProfile.Role.CUSTOMER
        )

        agent = self.create_user(
            "article_edit_owner",
            UserProfile.Role.AGENT
        )

        category = KnowledgeCategory.objects.create(
            name="Customer Editing",
            description="Customer editing permission test"
        )

        article = KnowledgeArticle.objects.create(
            title="Original Article",
            content="Original content.",
            category=category,
            author=agent,
            status=KnowledgeArticle.Status.PUBLISHED,
            published_at=timezone.now()
        )

        self.client.force_authenticate(user=customer)

        response = self.client.patch(
            f"/api/knowledge/articles/{article.id}/",
            {"title": "Customer Modified Article"},
            format="json"
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_403_FORBIDDEN
        )

        article.refresh_from_db()

        self.assertEqual(article.title, "Original Article")
        # 51. Only Admin can delete Knowledge Articles

    def test_only_admin_can_delete_knowledge_article(self):

        agent = self.create_user(
            "article_delete_agent",
            UserProfile.Role.AGENT
        )

        admin = self.create_user(
            "article_delete_admin",
            UserProfile.Role.ADMIN
        )

        category = KnowledgeCategory.objects.create(
            name="Deletion Help",
            description="Article deletion tests"
        )

        article = KnowledgeArticle.objects.create(
            title="Article to Delete",
            content="Testing deletion permissions.",
            category=category,
            author=admin,
            status=KnowledgeArticle.Status.DRAFT
        )

        # Agent attempts to delete
        self.client.force_authenticate(user=agent)

        agent_response = self.client.delete(
            f"/api/knowledge/articles/{article.id}/"
        )

        self.assertEqual(
            agent_response.status_code,
            status.HTTP_403_FORBIDDEN
        )

        self.assertTrue(
            KnowledgeArticle.objects.filter(id=article.id).exists()
        )

        # Admin attempts to delete
        self.client.force_authenticate(user=admin)

        admin_response = self.client.delete(
            f"/api/knowledge/articles/{article.id}/"
        )

        self.assertEqual(
            admin_response.status_code,
            status.HTTP_204_NO_CONTENT
        )

        self.assertFalse(
            KnowledgeArticle.objects.filter(id=article.id).exists()
        )
        # 52. Only Admin can publish Knowledge Articles

    def test_only_admin_can_publish_knowledge_article(self):

        agent = self.create_user(
            "article_publish_agent",
            UserProfile.Role.AGENT
        )

        admin = self.create_user(
            "article_publish_admin",
            UserProfile.Role.ADMIN
        )

        category = KnowledgeCategory.objects.create(
            name="Publishing Help",
            description="Article publishing tests"
        )

        article = KnowledgeArticle.objects.create(
            title="Article Ready to Publish",
            content="This article is ready.",
            category=category,
            author=agent,
            status=KnowledgeArticle.Status.DRAFT
        )

        # Agent attempts to publish
        self.client.force_authenticate(user=agent)

        agent_response = self.client.post(
            f"/api/knowledge/articles/{article.id}/publish/"
        )

        self.assertEqual(
            agent_response.status_code,
            status.HTTP_403_FORBIDDEN
        )

        article.refresh_from_db()
        self.assertEqual(article.status, KnowledgeArticle.Status.DRAFT)

        # Admin publishes the article
        self.client.force_authenticate(user=admin)

        admin_response = self.client.post(
            f"/api/knowledge/articles/{article.id}/publish/"
        )

        self.assertEqual(
            admin_response.status_code,
            status.HTTP_200_OK
        )

        article.refresh_from_db()

        self.assertEqual(
            article.status,
            KnowledgeArticle.Status.PUBLISHED
        )

        self.assertIsNotNone(article.published_at)
        # 53. Already published Knowledge Article cannot be published again

    def test_already_published_article_cannot_be_published_again(self):

        admin = self.create_user(
            "article_duplicate_publish_admin",
            UserProfile.Role.ADMIN
        )

        category = KnowledgeCategory.objects.create(
            name="Published Help",
            description="Duplicate publishing test"
        )

        article = KnowledgeArticle.objects.create(
            title="Already Published Article",
            content="This article is already published.",
            category=category,
            author=admin,
            status=KnowledgeArticle.Status.PUBLISHED,
            published_at=timezone.now()
        )

        self.client.force_authenticate(user=admin)

        response = self.client.post(
            f"/api/knowledge/articles/{article.id}/publish/"
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_400_BAD_REQUEST
        )

        self.assertEqual(
            response.data["message"],
            "Article is already published."
        )
        # 54. Agent and Admin can create FAQs

    def test_agent_and_admin_can_create_faq(self):

        agent = self.create_user(
            "faq_create_agent",
            UserProfile.Role.AGENT
        )

        admin = self.create_user(
            "faq_create_admin",
            UserProfile.Role.ADMIN
        )

        category = KnowledgeCategory.objects.create(
            name="FAQ Support",
            description="Frequently asked questions"
        )

        for user in [agent, admin]:

            self.client.force_authenticate(user=user)

            response = self.client.post(
                "/api/faqs/",
                {
                    "question": f"Question by {user.username}?",
                    "answer": "This is the answer.",
                    "category": category.id
                },
                format="json"
            )

            self.assertEqual(
                response.status_code,
                status.HTTP_201_CREATED
            )

            faq = FAQ.objects.get(
                question=f"Question by {user.username}?"
            )

            self.assertEqual(faq.author, user)
            self.assertEqual(faq.status, FAQ.Status.DRAFT)

        self.assertEqual(FAQ.objects.count(), 2)
        # 55. Customer cannot create FAQs

    def test_customer_cannot_create_faq(self):

        customer = self.create_user(
            "faq_create_customer",
            UserProfile.Role.CUSTOMER
        )

        category = KnowledgeCategory.objects.create(
            name="Customer FAQ",
            description="Customer FAQ permission test"
        )

        self.client.force_authenticate(user=customer)

        response = self.client.post(
            "/api/faqs/",
            {
                "question": "Can I create an FAQ?",
                "answer": "This should not be saved.",
                "category": category.id
            },
            format="json"
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_403_FORBIDDEN
        )

        self.assertEqual(FAQ.objects.count(), 0)
        # 56. Customers can see only published FAQs

    def test_customer_sees_only_published_faqs(self):

        customer = self.create_user(
            "faq_view_customer",
            UserProfile.Role.CUSTOMER
        )

        agent = self.create_user(
            "faq_view_agent",
            UserProfile.Role.AGENT
        )

        category = KnowledgeCategory.objects.create(
            name="FAQ Visibility",
            description="FAQ visibility tests"
        )

        FAQ.objects.create(
            question="How do I reset my password?",
            answer="Use the password reset option.",
            category=category,
            author=agent,
            status=FAQ.Status.PUBLISHED,
            published_at=timezone.now()
        )

        FAQ.objects.create(
            question="How do I change my account email?",
            answer="This answer is still being prepared.",
            category=category,
            author=agent,
            status=FAQ.Status.DRAFT
        )

        self.client.force_authenticate(user=customer)

        response = self.client.get("/api/faqs/")

        self.assertEqual(response.status_code, status.HTTP_200_OK)

        questions = [faq["question"] for faq in response.data]

        self.assertIn("How do I reset my password?", questions)
        self.assertNotIn("How do I change my account email?", questions)
        self.assertEqual(len(questions), 1)
        # 57. Agents and Admins can see all FAQs

    def test_agent_and_admin_see_all_faqs(self):

        agent = self.create_user(
            "faq_all_agent",
            UserProfile.Role.AGENT
        )

        admin = self.create_user(
            "faq_all_admin",
            UserProfile.Role.ADMIN
        )

        category = KnowledgeCategory.objects.create(
            name="FAQ Internal",
            description="Internal FAQ visibility tests"
        )

        FAQ.objects.create(
            question="Published FAQ question?",
            answer="Published answer.",
            category=category,
            author=admin,
            status=FAQ.Status.PUBLISHED,
            published_at=timezone.now()
        )

        FAQ.objects.create(
            question="Draft FAQ question?",
            answer="Draft answer.",
            category=category,
            author=admin,
            status=FAQ.Status.DRAFT
        )

        for user in [agent, admin]:

            self.client.force_authenticate(user=user)

            response = self.client.get("/api/faqs/")

            self.assertEqual(
                response.status_code,
                status.HTTP_200_OK
            )

            questions = [faq["question"] for faq in response.data]

            self.assertIn("Published FAQ question?", questions)
            self.assertIn("Draft FAQ question?", questions)
            self.assertEqual(len(questions), 2)
        # 58. Customer cannot access a Draft FAQ

    def test_customer_cannot_access_draft_faq(self):

        customer = self.create_user(
            "faq_draft_customer",
            UserProfile.Role.CUSTOMER
        )

        agent = self.create_user(
            "faq_draft_agent",
            UserProfile.Role.AGENT
        )

        category = KnowledgeCategory.objects.create(
            name="FAQ Private",
            description="Private FAQ tests"
        )

        faq = FAQ.objects.create(
            question="Private draft question?",
            answer="This answer must remain private.",
            category=category,
            author=agent,
            status=FAQ.Status.DRAFT
        )

        self.client.force_authenticate(user=customer)

        response = self.client.get(
            f"/api/faqs/{faq.id}/"
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_404_NOT_FOUND
        )
        # 59. Agent and Admin can edit FAQs

    def test_agent_and_admin_can_edit_faq(self):

        agent = self.create_user(
            "faq_edit_agent",
            UserProfile.Role.AGENT
        )

        admin = self.create_user(
            "faq_edit_admin",
            UserProfile.Role.ADMIN
        )

        category = KnowledgeCategory.objects.create(
            name="FAQ Editing",
            description="FAQ editing tests"
        )

        faq = FAQ.objects.create(
            question="Original FAQ question?",
            answer="Original answer.",
            category=category,
            author=admin,
            status=FAQ.Status.DRAFT
        )

        for user in [agent, admin]:

            self.client.force_authenticate(user=user)

            response = self.client.patch(
                f"/api/faqs/{faq.id}/",
                {
                    "answer": f"Updated by {user.username}."
                },
                format="json"
            )

            self.assertEqual(
                response.status_code,
                status.HTTP_200_OK
            )

            faq.refresh_from_db()

            self.assertEqual(
                faq.answer,
                f"Updated by {user.username}."
            )
        # 60. Customer cannot edit FAQs

    def test_customer_cannot_edit_faq(self):

        customer = self.create_user(
            "faq_edit_customer",
            UserProfile.Role.CUSTOMER
        )

        agent = self.create_user(
            "faq_edit_owner",
            UserProfile.Role.AGENT
        )

        category = KnowledgeCategory.objects.create(
            name="FAQ Customer Editing",
            description="Customer FAQ editing tests"
        )

        faq = FAQ.objects.create(
            question="Original FAQ question?",
            answer="Original answer.",
            category=category,
            author=agent,
            status=FAQ.Status.PUBLISHED,
            published_at=timezone.now()
        )

        self.client.force_authenticate(user=customer)

        response = self.client.patch(
            f"/api/faqs/{faq.id}/",
            {"answer": "Modified by customer."},
            format="json"
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_403_FORBIDDEN
        )

        faq.refresh_from_db()

        self.assertEqual(faq.answer, "Original answer.")
        # 61. Only Admin can delete FAQs

    def test_only_admin_can_delete_faq(self):

        agent = self.create_user(
            "faq_delete_agent",
            UserProfile.Role.AGENT
        )

        admin = self.create_user(
            "faq_delete_admin",
            UserProfile.Role.ADMIN
        )

        category = KnowledgeCategory.objects.create(
            name="FAQ Deletion",
            description="FAQ deletion tests"
        )

        faq = FAQ.objects.create(
            question="FAQ to delete?",
            answer="Testing deletion permissions.",
            category=category,
            author=admin,
            status=FAQ.Status.DRAFT
        )

        # Agent attempts to delete
        self.client.force_authenticate(user=agent)

        agent_response = self.client.delete(
            f"/api/faqs/{faq.id}/"
        )

        self.assertEqual(
            agent_response.status_code,
            status.HTTP_403_FORBIDDEN
        )

        self.assertTrue(
            FAQ.objects.filter(id=faq.id).exists()
        )

        # Admin attempts to delete
        self.client.force_authenticate(user=admin)

        admin_response = self.client.delete(
            f"/api/faqs/{faq.id}/"
        )

        self.assertEqual(
            admin_response.status_code,
            status.HTTP_204_NO_CONTENT
        )

        self.assertFalse(
            FAQ.objects.filter(id=faq.id).exists()
        )
        # 62. Only Admin can publish FAQs

    def test_only_admin_can_publish_faq(self):

        agent = self.create_user(
            "faq_publish_agent",
            UserProfile.Role.AGENT
        )

        admin = self.create_user(
            "faq_publish_admin",
            UserProfile.Role.ADMIN
        )

        category = KnowledgeCategory.objects.create(
            name="FAQ Publishing",
            description="FAQ publishing tests"
        )

        faq = FAQ.objects.create(
            question="Ready to publish?",
            answer="This FAQ is ready.",
            category=category,
            author=agent,
            status=FAQ.Status.DRAFT
        )

        # Agent attempts to publish
        self.client.force_authenticate(user=agent)

        agent_response = self.client.post(
            f"/api/faqs/{faq.id}/publish/"
        )

        self.assertEqual(
            agent_response.status_code,
            status.HTTP_403_FORBIDDEN
        )

        faq.refresh_from_db()

        self.assertEqual(faq.status, FAQ.Status.DRAFT)

        # Admin publishes the FAQ
        self.client.force_authenticate(user=admin)

        admin_response = self.client.post(
            f"/api/faqs/{faq.id}/publish/"
        )

        self.assertEqual(
            admin_response.status_code,
            status.HTTP_200_OK
        )

        faq.refresh_from_db()

        self.assertEqual(
            faq.status,
            FAQ.Status.PUBLISHED
        )

        self.assertIsNotNone(faq.published_at)
        # 63. Already published FAQ cannot be published again

    def test_already_published_faq_cannot_be_published_again(self):

        admin = self.create_user(
            "faq_duplicate_publish_admin",
            UserProfile.Role.ADMIN
        )

        category = KnowledgeCategory.objects.create(
            name="Published FAQ",
            description="Duplicate FAQ publishing test"
        )

        faq = FAQ.objects.create(
            question="Already published question?",
            answer="This FAQ is already published.",
            category=category,
            author=admin,
            status=FAQ.Status.PUBLISHED,
            published_at=timezone.now()
        )

        self.client.force_authenticate(user=admin)

        response = self.client.post(
            f"/api/faqs/{faq.id}/publish/"
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_400_BAD_REQUEST
        )

        self.assertEqual(
            response.data["message"],
            "FAQ is already published."
        )

    # 64. Customer can send and retrieve messages on their own ticket
    def test_customer_can_send_and_retrieve_ticket_messages(self):

        customer = self.create_user(
            "message_customer",
            UserProfile.Role.CUSTOMER
        )
        agent = self.create_user(
            "message_agent",
            UserProfile.Role.AGENT
        )

        ticket = self.create_ticket(customer, agent)

        self.client.force_authenticate(user=customer)

        url = f"/api/tickets/{ticket.id}/messages/"

        # Customer sends a message
        post_response = self.client.post(
            url,
            {"message": "I still need help with my payment."},
            format="json"
        )

        self.assertEqual(
            post_response.status_code,
            status.HTTP_201_CREATED
        )

        self.assertEqual(
            post_response.data["sender_username"],
            customer.username
        )

        self.assertEqual(
            TicketMessage.objects.filter(ticket=ticket).count(),
            1
        )

        # Customer retrieves the conversation
        get_response = self.client.get(url)

        self.assertEqual(
            get_response.status_code,
            status.HTTP_200_OK
        )

        self.assertEqual(len(get_response.data), 1)

        self.assertEqual(
            get_response.data[0]["message"],
            "I still need help with my payment."
        )

    # 65. Customer cannot access another customer's messages
    def test_customer_cannot_access_other_ticket_messages(self):

        customer1 = self.create_user(
            "message_customer1",
            UserProfile.Role.CUSTOMER
        )
        customer2 = self.create_user(
            "message_customer2",
            UserProfile.Role.CUSTOMER
        )
        agent = self.create_user(
            "message_agent2",
            UserProfile.Role.AGENT
        )

        ticket = self.create_ticket(customer1, agent)

        self.client.force_authenticate(user=customer2)

        url = f"/api/tickets/{ticket.id}/messages/"

        get_response = self.client.get(url)

        post_response = self.client.post(
            url,
            {"message": "Unauthorized message."},
            format="json"
        )

        self.assertEqual(
            get_response.status_code,
            status.HTTP_403_FORBIDDEN
        )

        self.assertEqual(
            post_response.status_code,
            status.HTTP_403_FORBIDDEN
        )

        self.assertEqual(TicketMessage.objects.count(), 0)

    # 66. Assigned Agent can reply to a ticket
    def test_assigned_agent_can_reply_to_ticket(self):

        customer = self.create_user(
            "message_customer3",
            UserProfile.Role.CUSTOMER
        )
        agent = self.create_user(
            "message_agent3",
            UserProfile.Role.AGENT
        )

        ticket = self.create_ticket(customer, agent)

        self.client.force_authenticate(user=agent)

        response = self.client.post(
            f"/api/tickets/{ticket.id}/messages/",
            {"message": "We are investigating your issue."},
            format="json"
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_201_CREATED
        )

        self.assertEqual(
            response.data["sender_username"],
            agent.username
        )

        self.assertEqual(
            TicketMessage.objects.filter(ticket=ticket).count(),
            1
        )

    # 67. Unassigned Agent cannot access or reply to a ticket
    def test_unassigned_agent_cannot_access_ticket_messages(self):

        customer = self.create_user(
            "message_customer4",
            UserProfile.Role.CUSTOMER
        )
        assigned_agent = self.create_user(
            "message_assigned_agent",
            UserProfile.Role.AGENT
        )
        other_agent = self.create_user(
            "message_other_agent",
            UserProfile.Role.AGENT
        )

        ticket = self.create_ticket(customer, assigned_agent)

        self.client.force_authenticate(user=other_agent)

        url = f"/api/tickets/{ticket.id}/messages/"

        get_response = self.client.get(url)

        post_response = self.client.post(
            url,
            {"message": "Unauthorized agent reply."},
            format="json"
        )

        self.assertEqual(
            get_response.status_code,
            status.HTTP_403_FORBIDDEN
        )

        self.assertEqual(
            post_response.status_code,
            status.HTTP_403_FORBIDDEN
        )

        self.assertEqual(TicketMessage.objects.count(), 0)

    # 68. Admin can access and send ticket messages
    def test_admin_can_access_and_send_ticket_messages(self):

        customer = self.create_user(
            "message_customer5",
            UserProfile.Role.CUSTOMER
        )
        agent = self.create_user(
            "message_agent5",
            UserProfile.Role.AGENT
        )
        admin = self.create_user(
            "message_admin",
            UserProfile.Role.ADMIN
        )

        ticket = self.create_ticket(customer, agent)

        self.client.force_authenticate(user=admin)

        url = f"/api/tickets/{ticket.id}/messages/"

        post_response = self.client.post(
            url,
            {"message": "Admin is reviewing this ticket."},
            format="json"
        )

        self.assertEqual(
            post_response.status_code,
            status.HTTP_201_CREATED
        )

        get_response = self.client.get(url)

        self.assertEqual(
            get_response.status_code,
            status.HTTP_200_OK
        )

        self.assertEqual(len(get_response.data), 1)

        self.assertEqual(
            get_response.data[0]["sender_username"],
            admin.username
        )

    # 69. Agent's first message automatically records SLA first response
    def test_agent_first_message_records_sla_first_response(self):

        customer = self.create_user(
            "sla_message_customer",
            UserProfile.Role.CUSTOMER
        )
        agent = self.create_user(
            "sla_message_agent",
            UserProfile.Role.AGENT
        )

        ticket = self.create_ticket(customer, agent)

        policy, created = SLAPolicy.objects.get_or_create(
            priority=ticket.priority,
            defaults={
                "response_time_minutes": 120,
                "resolution_time_minutes": 1440
            }
        )

        sla = TicketSLA.objects.create(
            ticket=ticket,
            policy=policy,
            response_target_minutes=120,
            resolution_target_minutes=1440,
            response_deadline=timezone.now() + timedelta(hours=2),
            resolution_deadline=timezone.now() + timedelta(hours=24)
        )

        self.client.force_authenticate(user=agent)

        url = f"/api/tickets/{ticket.id}/messages/"

        response = self.client.post(
            url,
            {"message": "We are looking into your issue."},
            format="json"
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_201_CREATED
        )

        sla.refresh_from_db()

        self.assertIsNotNone(sla.first_response_at)

        self.assertEqual(
            sla.response_status,
            TicketSLA.Status.MET
        )

        self.assertEqual(
            ticket.history.filter(
                action=TicketHistory.Action.FIRST_RESPONSE_RECORDED
            ).count(),
            1
        )

    # 70. Subsequent agent messages do not overwrite first response
    def test_subsequent_agent_messages_do_not_overwrite_first_response(self):

        customer = self.create_user(
            "repeat_message_customer",
            UserProfile.Role.CUSTOMER
        )
        agent = self.create_user(
            "repeat_message_agent",
            UserProfile.Role.AGENT
        )

        ticket = self.create_ticket(customer, agent)

        policy, created = SLAPolicy.objects.get_or_create(
            priority=ticket.priority,
            defaults={
                "response_time_minutes": 120,
                "resolution_time_minutes": 1440
            }
        )

        sla = TicketSLA.objects.create(
            ticket=ticket,
            policy=policy,
            response_target_minutes=120,
            resolution_target_minutes=1440,
            response_deadline=timezone.now() + timedelta(hours=2),
            resolution_deadline=timezone.now() + timedelta(hours=24)
        )

        self.client.force_authenticate(user=agent)

        url = f"/api/tickets/{ticket.id}/messages/"

        # First agent reply
        first_response = self.client.post(
            url,
            {"message": "We are checking your issue."},
            format="json"
        )

        self.assertEqual(
            first_response.status_code,
            status.HTTP_201_CREATED
        )

        sla.refresh_from_db()
        original_first_response = sla.first_response_at

        # Second agent reply
        second_response = self.client.post(
            url,
            {"message": "We have an update for you."},
            format="json"
        )

        self.assertEqual(
            second_response.status_code,
            status.HTTP_201_CREATED
        )

        sla.refresh_from_db()

        self.assertEqual(
            sla.first_response_at,
            original_first_response
        )

        self.assertEqual(
            ticket.history.filter(
                action=TicketHistory.Action.FIRST_RESPONSE_RECORDED
            ).count(),
            1
        )

        self.assertEqual(
            TicketMessage.objects.filter(ticket=ticket).count(),
            2
        )

    @patch(
        "ticket_Api.views.generate_reply",
        return_value="We are checking your payment issue. We will update you shortly."
    )
    def test_assigned_agent_can_generate_ai_reply(self, mock_generate_reply):

        customer = self.create_user(
            "ai_reply_customer",
            UserProfile.Role.CUSTOMER
        )

        agent = self.create_user(
            "ai_reply_agent",
            UserProfile.Role.AGENT
        )

        ticket = self.create_ticket(customer, agent)

        self.client.force_authenticate(user=agent)

        response = self.client.post(
            f"/api/tickets/{ticket.id}/ai-reply/"
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)

        self.assertEqual(
            response.data["suggested_reply"],
            "We are checking your payment issue. We will update you shortly."
        )

        self.assertEqual(
            TicketMessage.objects.filter(ticket=ticket).count(),
            0
        )

        mock_generate_reply.assert_called_once()

    def test_customer_cannot_generate_ai_reply(self):

        customer = self.create_user(
            "ai_reply_customer_denied",
            UserProfile.Role.CUSTOMER
        )

        agent = self.create_user(
            "ai_reply_assigned_agent",
            UserProfile.Role.AGENT
        )

        ticket = self.create_ticket(customer, agent)

        self.client.force_authenticate(user=customer)

        response = self.client.post(
            f"/api/tickets/{ticket.id}/ai-reply/"
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_403_FORBIDDEN
        )

        self.assertEqual(
            TicketMessage.objects.filter(ticket=ticket).count(),
            0
        )

    def test_unassigned_agent_cannot_generate_ai_reply(self):

        customer = self.create_user(
            "ai_reply_customer_unassigned",
            UserProfile.Role.CUSTOMER
        )

        assigned_agent = self.create_user(
            "ai_reply_assigned",
            UserProfile.Role.AGENT
        )

        another_agent = self.create_user(
            "ai_reply_unassigned",
            UserProfile.Role.AGENT
        )

        ticket = self.create_ticket(customer, assigned_agent)

        self.client.force_authenticate(user=another_agent)

        response = self.client.post(
            f"/api/tickets/{ticket.id}/ai-reply/"
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_403_FORBIDDEN
        )

        self.assertEqual(
            TicketMessage.objects.filter(ticket=ticket).count(),
            0
        )

    @patch(
        "ticket_Api.views.generate_reply",
        return_value="Our support team is reviewing your issue."
    )
    def test_admin_can_generate_ai_reply(self, mock_generate_reply):

        customer = self.create_user(
            "ai_reply_admin_customer",
            UserProfile.Role.CUSTOMER
        )

        agent = self.create_user(
            "ai_reply_admin_agent",
            UserProfile.Role.AGENT
        )

        admin = self.create_user(
            "ai_reply_admin",
            UserProfile.Role.ADMIN
        )

        ticket = self.create_ticket(customer, agent)

        self.client.force_authenticate(user=admin)

        response = self.client.post(
            f"/api/tickets/{ticket.id}/ai-reply/"
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)

        self.assertEqual(
            response.data["suggested_reply"],
            "Our support team is reviewing your issue."
        )

        self.assertEqual(
            TicketMessage.objects.filter(ticket=ticket).count(),
            0
        )

        mock_generate_reply.assert_called_once()

    @patch(
        "ticket_Api.views.generate_reply",
        side_effect=Exception("Gemini API unavailable")
    )
    def test_ai_reply_returns_service_unavailable_when_gemini_fails(
        self,
        mock_generate_reply
    ):

        customer = self.create_user(
            "ai_error_customer",
            UserProfile.Role.CUSTOMER
        )

        agent = self.create_user(
            "ai_error_agent",
            UserProfile.Role.AGENT
        )

        ticket = self.create_ticket(customer, agent)

        self.client.force_authenticate(user=agent)

        response = self.client.post(
            f"/api/tickets/{ticket.id}/ai-reply/"
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_503_SERVICE_UNAVAILABLE
        )

        self.assertEqual(
            response.data["error"],
            "AI reply generation is currently unavailable."
        )

        self.assertEqual(
            TicketMessage.objects.filter(ticket=ticket).count(),
            0
        )

    @patch("ticket_Api.ai_services.reply_generator.get_gemini_client")
    def test_ai_reply_uses_only_latest_30_messages(self, mock_get_client):

        customer = self.create_user(
            "history_customer",
            UserProfile.Role.CUSTOMER
        )

        agent = self.create_user(
            "history_agent",
            UserProfile.Role.AGENT
        )

        ticket = self.create_ticket(customer, agent)

        for i in range(35):
            TicketMessage.objects.create(
                ticket=ticket,
                sender=customer,
                message=f"Customer message {i + 1}"
            )

        mock_interaction = mock_get_client.return_value.interactions.create
        mock_interaction.return_value.output_text = "Suggested reply"

        messages = ticket.messages.select_related("sender").order_by(
            "created_at", "id"
        )

        result = generate_reply(ticket, messages)

        prompt = mock_interaction.call_args.kwargs["input"]

        self.assertEqual(result, "Suggested reply")

        self.assertNotIn("Customer message 5", prompt)
        self.assertIn("Customer message 6", prompt)
        self.assertIn("Customer message 35", prompt)

        self.assertEqual(
            prompt.count("Customer message"),
            30
        )
