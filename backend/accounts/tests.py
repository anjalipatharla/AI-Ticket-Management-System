from unittest.mock import patch

from django.contrib.auth.models import User
from django.contrib.auth.tokens import default_token_generator
from django.core import mail
from django.test import override_settings
from django.utils.encoding import force_bytes
from django.utils.http import urlsafe_base64_encode
from rest_framework import status
from rest_framework.test import APITestCase
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework_simplejwt.token_blacklist.models import BlacklistedToken

from .models import GoogleIdentity, UserProfile


class AuthenticationAndAuthorizationTests(APITestCase):
    password = "V3ry$tr0ng_Password_2026!!"

    def make_user(self, username, email, role=UserProfile.Role.CUSTOMER):
        user = User.objects.create_user(
            username=username,
            email=email,
            password=self.password,
        )
        user.profile.role = role
        user.profile.save(update_fields=["role", "updated_at"])
        return user

    def google_claims(self, sub="google-sub-001", email="google@example.com"):
        return {
            "sub": sub,
            "email": email,
            "email_verified": True,
            "given_name": "Google",
            "family_name": "User",
        }

    def verify_google(self, claims):
        return (
            patch("accounts.serializers.config", return_value="test-google-client"),
            patch(
                "accounts.serializers.id_token.verify_oauth2_token",
                return_value=claims,
            ),
        )

    def test_email_registration_creates_customer_and_returns_jwt(self):
        response = self.client.post(
            "/api/accounts/register/",
            {
                "username": "newcustomer",
                "first_name": "New",
                "last_name": "Customer",
                "email": "NEW.CUSTOMER@example.com",
                "password": self.password,
                "confirm_password": self.password,
                "role": "ADMIN",
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertIn("access", response.data)
        self.assertIn("refresh", response.data)
        self.assertEqual(response.data["user"]["role"], UserProfile.Role.CUSTOMER)

        user = User.objects.get(username="newcustomer")
        self.assertEqual(user.email, "new.customer@example.com")
        self.assertEqual(user.profile.role, UserProfile.Role.CUSTOMER)

    def test_registration_rejects_duplicate_email(self):
        self.make_user("firstuser", "same@example.com")

        response = self.client.post(
            "/api/accounts/register/",
            {
                "username": "seconduser",
                "first_name": "Second",
                "email": "SAME@example.com",
                "password": self.password,
                "confirm_password": self.password,
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(User.objects.filter(email__iexact="same@example.com").count(), 1)

    def test_username_password_login_returns_jwt(self):
        user = self.make_user("loginuser", "login@example.com")

        response = self.client.post(
            "/api/accounts/login/",
            {"username": user.username, "password": self.password},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn("access", response.data)
        self.assertIn("refresh", response.data)

    def test_refresh_endpoint_returns_new_access_token(self):
        user = self.make_user("refreshuser", "refresh@example.com")
        refresh = str(RefreshToken.for_user(user))

        response = self.client.post(
            "/api/accounts/token/refresh/",
            {"refresh": refresh},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn("access", response.data)

    def test_logout_blacklists_users_own_refresh_token(self):
        user = self.make_user("logoutuser", "logout@example.com")
        refresh = RefreshToken.for_user(user)
        token_jti = refresh["jti"]
        self.client.force_authenticate(user=user)

        response = self.client.post(
            "/api/accounts/logout/",
            {"refresh": str(refresh)},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(
            BlacklistedToken.objects.filter(token__jti=token_jti).exists()
        )

    def test_logout_rejects_another_users_refresh_token(self):
        user = self.make_user("logoutowner", "owner@example.com")
        other_user = self.make_user("otherowner", "other@example.com")
        self.client.force_authenticate(user=user)

        response = self.client.post(
            "/api/accounts/logout/",
            {"refresh": str(RefreshToken.for_user(other_user))},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_profile_cannot_change_application_role(self):
        user = self.make_user("profileuser", "profile@example.com")
        self.client.force_authenticate(user=user)

        response = self.client.patch(
            "/api/accounts/profile/",
            {"phone_number": "9876543210", "role": "ADMIN"},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        user.profile.refresh_from_db()
        self.assertEqual(user.profile.role, UserProfile.Role.CUSTOMER)
        self.assertEqual(user.profile.phone_number, "9876543210")

    def test_google_login_creates_new_user_and_identity(self):
        claims = self.google_claims()
        config_patch, verify_patch = self.verify_google(claims)

        with config_patch, verify_patch:
            response = self.client.post(
                "/api/accounts/google/",
                {"id_token": "mock-google-id-token"},
                format="json",
            )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn("access", response.data)
        self.assertIn("refresh", response.data)

        user = User.objects.get(email="google@example.com")
        self.assertFalse(user.has_usable_password())
        self.assertEqual(user.profile.role, UserProfile.Role.CUSTOMER)
        self.assertTrue(
            GoogleIdentity.objects.filter(
                user=user,
                google_sub="google-sub-001",
            ).exists()
        )

    def test_google_login_uses_existing_google_identity(self):
        user = self.make_user("linkeduser", "google@example.com")
        GoogleIdentity.objects.create(
            user=user,
            google_sub="google-sub-002",
            email="google@example.com",
        )
        claims = self.google_claims(
            sub="google-sub-002",
            email="google@example.com",
        )
        config_patch, verify_patch = self.verify_google(claims)

        with config_patch, verify_patch:
            response = self.client.post(
                "/api/accounts/google/",
                {"id_token": "mock-google-id-token"},
                format="json",
            )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(GoogleIdentity.objects.count(), 1)

    def test_google_login_does_not_auto_link_existing_email(self):
        self.make_user("passworduser", "google@example.com")
        claims = self.google_claims()
        config_patch, verify_patch = self.verify_google(claims)

        with config_patch, verify_patch:
            response = self.client.post(
                "/api/accounts/google/",
                {"id_token": "mock-google-id-token"},
                format="json",
            )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(GoogleIdentity.objects.count(), 0)

    def test_google_link_requires_authenticated_user(self):
        response = self.client.post(
            "/api/accounts/google/link/",
            {"id_token": "mock-google-id-token"},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_google_link_requires_matching_verified_email(self):
        user = self.make_user("linkuser", "local@example.com")
        self.client.force_authenticate(user=user)
        claims = self.google_claims(email="different@example.com")
        config_patch, verify_patch = self.verify_google(claims)

        with config_patch, verify_patch:
            response = self.client.post(
                "/api/accounts/google/link/",
                {"id_token": "mock-google-id-token"},
                format="json",
            )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertFalse(GoogleIdentity.objects.filter(user=user).exists())

    def test_google_link_succeeds_for_same_verified_email(self):
        user = self.make_user("linkuser", "google@example.com")
        self.client.force_authenticate(user=user)
        claims = self.google_claims()
        config_patch, verify_patch = self.verify_google(claims)

        with config_patch, verify_patch:
            response = self.client.post(
                "/api/accounts/google/link/",
                {"id_token": "mock-google-id-token"},
                format="json",
            )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(GoogleIdentity.objects.filter(user=user).exists())

    def test_customer_cannot_change_user_roles(self):
        customer = self.make_user("customer", "customer@example.com")
        target = self.make_user("target", "target@example.com")
        self.client.force_authenticate(user=customer)

        response = self.client.patch(
            f"/api/accounts/users/{target.pk}/role/",
            {"role": UserProfile.Role.AGENT},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        target.profile.refresh_from_db()
        self.assertEqual(target.profile.role, UserProfile.Role.CUSTOMER)

    def test_application_admin_can_change_user_role(self):
        app_admin = self.make_user(
            "appadmin",
            "appadmin@example.com",
            UserProfile.Role.ADMIN,
        )
        target = self.make_user("target", "target@example.com")
        self.client.force_authenticate(user=app_admin)

        response = self.client.patch(
            f"/api/accounts/users/{target.pk}/role/",
            {"role": UserProfile.Role.AGENT},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        target.profile.refresh_from_db()
        self.assertEqual(target.profile.role, UserProfile.Role.AGENT)

    def test_last_active_application_admin_cannot_be_demoted(self):
        app_admin = self.make_user(
            "onlyadmin",
            "onlyadmin@example.com",
            UserProfile.Role.ADMIN,
        )
        self.client.force_authenticate(user=app_admin)

        response = self.client.patch(
            f"/api/accounts/users/{app_admin.pk}/role/",
            {"role": UserProfile.Role.CUSTOMER},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        app_admin.profile.refresh_from_db()
        self.assertEqual(app_admin.profile.role, UserProfile.Role.ADMIN)

    @override_settings(
        EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend",
        DEFAULT_FROM_EMAIL="noreply@example.com",
    )
    def test_forgot_password_sends_reset_instructions_without_returning_token(self):
        user = self.make_user("forgotuser", "forgot@example.com")

        response = self.client.post(
            "/api/accounts/forgot-password/",
            {"email": user.email},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(mail.outbox), 1)
        self.assertNotIn("token", response.data)
        self.assertIn("UID:", mail.outbox[0].body)
        self.assertIn("Token:", mail.outbox[0].body)

    def test_reset_password_changes_password(self):
        user = self.make_user("resetuser", "reset@example.com")
        uid = urlsafe_base64_encode(force_bytes(user.pk))
        token = default_token_generator.make_token(user)
        new_password = "An0ther$trong_Password_2026!!"

        response = self.client.post(
            "/api/accounts/reset-password/",
            {
                "uid": uid,
                "token": token,
                "new_password": new_password,
                "confirm_password": new_password,
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        user.refresh_from_db()
        self.assertTrue(user.check_password(new_password))
