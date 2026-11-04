from unittest.mock import patch

from django.contrib.auth.models import User
from django.core import mail
from django.test import TestCase
from rest_framework.test import APIClient, APIRequestFactory

from .models import GoogleIdentity, UserProfile
from .permissions import (
    IsApplicationAdmin,
    IsCustomer,
    IsManager,
    IsOwnerOrSupportTeam,
    IsSupportAgent,
)


class RolePermissionTests(TestCase):
    def setUp(self):
        self.customer = User.objects.create_user(
            username="customer", password="ExamplePass123!"
        )
        self.agent = User.objects.create_user(
            username="agent", password="ExamplePass123!"
        )
        self.manager = User.objects.create_user(
            username="manager", password="ExamplePass123!"
        )
        self.app_admin = User.objects.create_user(
            username="app-admin", password="ExamplePass123!"
        )
        for user, role in (
            (self.customer, UserProfile.Role.CUSTOMER),
            (self.agent, UserProfile.Role.AGENT),
            (self.manager, UserProfile.Role.MANAGER),
            (self.app_admin, UserProfile.Role.ADMIN),
        ):
            user.profile.role = role
            user.profile.save()
        self.client = APIClient()
        self.factory = APIRequestFactory()

    def test_customer_cannot_assign_roles(self):
        self.client.force_authenticate(self.customer)
        response = self.client.patch(
            f"/api/accounts/users/{self.agent.pk}/role/",
            {"role": "MANAGER"},
            format="json",
        )
        self.assertEqual(response.status_code, 403)

    def test_application_admin_can_assign_agent_role(self):
        self.client.force_authenticate(self.app_admin)
        response = self.client.patch(
            f"/api/accounts/users/{self.customer.pk}/role/",
            {"role": "AGENT"},
            format="json",
        )
        self.assertEqual(response.status_code, 200)
        self.customer.profile.refresh_from_db()
        self.assertEqual(self.customer.profile.role, UserProfile.Role.AGENT)

    def test_application_admin_cannot_assign_admin_role_through_api(self):
        self.client.force_authenticate(self.app_admin)
        response = self.client.patch(
            f"/api/accounts/users/{self.customer.pk}/role/",
            {"role": "ADMIN"},
            format="json",
        )
        self.assertEqual(response.status_code, 400)

    def test_role_permissions_match_profiles(self):
        request = self.factory.get("/")
        request.user = self.customer
        self.assertTrue(IsCustomer().has_permission(request, None))
        self.assertFalse(IsApplicationAdmin().has_permission(request, None))

        request.user = self.agent
        self.assertTrue(IsSupportAgent().has_permission(request, None))

        request.user = self.manager
        self.assertTrue(IsManager().has_permission(request, None))

    def test_django_superuser_flag_does_not_grant_application_admin_role(self):
        superuser = User.objects.create_superuser(
            username="django-root",
            email="root@example.com",
            password="ExamplePass123!",
        )
        superuser.profile.role = UserProfile.Role.CUSTOMER
        superuser.profile.save()
        request = self.factory.get("/")
        request.user = superuser
        self.assertFalse(IsApplicationAdmin().has_permission(request, None))

    def test_customer_can_access_own_object(self):
        class TicketStub:
            customer_id = None

        ticket = TicketStub()
        ticket.customer_id = self.customer.pk
        request = self.factory.get("/")
        request.user = self.customer
        self.assertTrue(
            IsOwnerOrSupportTeam().has_object_permission(request, None, ticket)
        )

    def test_customer_cannot_access_another_customers_object(self):
        class TicketStub:
            customer_id = None

        ticket = TicketStub()
        ticket.customer_id = self.agent.pk
        request = self.factory.get("/")
        request.user = self.customer
        self.assertFalse(
            IsOwnerOrSupportTeam().has_object_permission(request, None, ticket)
        )

    def test_support_agent_can_access_customer_object(self):
        class TicketStub:
            customer_id = None

        ticket = TicketStub()
        ticket.customer_id = self.customer.pk
        request = self.factory.get("/")
        request.user = self.agent
        self.assertTrue(
            IsOwnerOrSupportTeam().has_object_permission(request, None, ticket)
        )


class RegistrationTests(TestCase):
    def test_registration_creates_customer_profile_and_returns_jwt(self):
        response = self.client.post(
            "/api/accounts/register/",
            {
                "username": "newcustomer",
                "first_name": "New",
                "last_name": "Customer",
                "email": "newcustomer@example.com",
                "password": "SafeExamplePass123!",
                "confirm_password": "SafeExamplePass123!",
            },
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 201)
        user = User.objects.get(username="newcustomer")
        self.assertEqual(user.profile.role, UserProfile.Role.CUSTOMER)
        self.assertIn("access", response.json())
        self.assertIn("refresh", response.json())


class GoogleLoginTests(TestCase):
    @patch("accounts.serializers.config", return_value="test-client-id")
    @patch("accounts.serializers.id_token.verify_oauth2_token")
    def test_new_google_user_is_created_and_linked(self, verify_token, mock_config):
        verify_token.return_value = {
            "sub": "google-sub-123",
            "email": "new-google@example.com",
            "email_verified": True,
            "given_name": "Google",
            "family_name": "Customer",
        }
        response = self.client.post(
            "/api/accounts/google/",
            {"id_token": "mock-id-token"},
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 200)
        user = User.objects.get(email="new-google@example.com")
        identity = GoogleIdentity.objects.get(user=user)
        self.assertEqual(identity.google_sub, "google-sub-123")
        self.assertIn("access", response.json())
        self.assertIn("refresh", response.json())

    @patch("accounts.serializers.config", return_value="test-client-id")
    @patch("accounts.serializers.id_token.verify_oauth2_token")
    def test_existing_linked_google_user_can_login(self, verify_token, mock_config):
        user = User.objects.create_user(
            username="linked-user",
            email="linked@example.com",
            password="ExamplePass123!",
        )
        GoogleIdentity.objects.create(
            user=user,
            google_sub="linked-google-sub",
            email="linked@example.com",
        )
        verify_token.return_value = {
            "sub": "linked-google-sub",
            "email": "linked@example.com",
            "email_verified": True,
        }
        response = self.client.post(
            "/api/accounts/google/",
            {"id_token": "mock-id-token"},
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 200)

    @patch("accounts.serializers.config", return_value="test-client-id")
    @patch("accounts.serializers.id_token.verify_oauth2_token")
    def test_existing_email_is_not_automatically_linked(self, verify_token, mock_config):
        User.objects.create_user(
            username="local-user",
            email="same@example.com",
            password="ExamplePass123!",
        )
        verify_token.return_value = {
            "sub": "unlinked-google-sub",
            "email": "same@example.com",
            "email_verified": True,
        }
        response = self.client.post(
            "/api/accounts/google/",
            {"id_token": "mock-id-token"},
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 400)
        self.assertFalse(
            GoogleIdentity.objects.filter(google_sub="unlinked-google-sub").exists()
        )


class GoogleLinkTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="local-user",
            email="local@example.com",
            password="SafeExamplePass123!",
        )
        self.client = APIClient()
        self.client.force_authenticate(self.user)

    @patch("accounts.serializers.config", return_value="test-client-id")
    @patch("accounts.serializers.id_token.verify_oauth2_token")
    def test_authenticated_user_can_link_matching_verified_google_email(
        self, verify_token, mock_config
    ):
        verify_token.return_value = {
            "sub": "matching-google-sub",
            "email": "local@example.com",
            "email_verified": True,
        }
        response = self.client.post(
            "/api/accounts/google/link/",
            {"id_token": "mock-id-token"},
            format="json",
        )
        self.assertEqual(response.status_code, 200)
        self.assertTrue(
            GoogleIdentity.objects.filter(
                user=self.user,
                google_sub="matching-google-sub",
            ).exists()
        )

    @patch("accounts.serializers.config", return_value="test-client-id")
    @patch("accounts.serializers.id_token.verify_oauth2_token")
    def test_link_rejects_google_email_that_does_not_match_account(
        self, verify_token, mock_config
    ):
        verify_token.return_value = {
            "sub": "different-google-sub",
            "email": "someone-else@example.com",
            "email_verified": True,
        }
        response = self.client.post(
            "/api/accounts/google/link/",
            {"id_token": "mock-id-token"},
            format="json",
        )
        self.assertEqual(response.status_code, 400)
        self.assertFalse(
            GoogleIdentity.objects.filter(google_sub="different-google-sub").exists()
        )

    @patch("accounts.serializers.config", return_value="test-client-id")
    @patch("accounts.serializers.id_token.verify_oauth2_token")
    def test_legacy_google_user_is_upgraded_to_google_identity(
        self, verify_token, mock_config
    ):
        user = User.objects.create_user(
            username="google_legacy-sub",
            email="legacy@example.com",
        )
        self.assertFalse(user.has_usable_password())
        verify_token.return_value = {
            "sub": "legacy-sub",
            "email": "legacy@example.com",
            "email_verified": True,
        }
        response = self.client.post(
            "/api/accounts/google/",
            {"id_token": "mock-id-token"},
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 200)
        self.assertTrue(
            GoogleIdentity.objects.filter(
                user=user, google_sub="legacy-sub"
            ).exists()
        )
