
from django.contrib.auth.models import User
from django.utils import timezone

from rest_framework import status
from rest_framework.test import APITestCase

from accounts.models import UserProfile
from .models import Complaint, Ticket, TicketHistory


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
