import binascii
import hashlib

from decouple import config
from django.contrib.auth.models import User
from django.contrib.auth.password_validation import validate_password
from django.contrib.auth.tokens import default_token_generator
from django.core.mail import send_mail
from django.db import IntegrityError, transaction
from django.utils.encoding import force_bytes, force_str
from django.utils.http import urlsafe_base64_decode, urlsafe_base64_encode
from google.auth.transport import requests as google_requests
from google.oauth2 import id_token
from rest_framework import serializers
from rest_framework_simplejwt.exceptions import TokenError
from rest_framework_simplejwt.tokens import RefreshToken

from .models import GoogleIdentity, UserProfile


class RegisterSerializer(serializers.Serializer):
    username = serializers.CharField(max_length=150)
    first_name = serializers.CharField(max_length=150)
    last_name = serializers.CharField(
        max_length=150,
        required=False,
        allow_blank=True,
    )
    email = serializers.EmailField()
    password = serializers.CharField(
        write_only=True,
        validators=[validate_password],
    )
    confirm_password = serializers.CharField(write_only=True)

    def validate_username(self, value):
        value = value.strip()
        if not value:
            raise serializers.ValidationError("Username is required.")
        if User.objects.filter(username__iexact=value).exists():
            raise serializers.ValidationError("This username is already taken.")
        return value

    def validate_email(self, value):
        value = value.strip().lower()
        if User.objects.filter(email__iexact=value).exists():
            raise serializers.ValidationError(
                "This email is already registered."
            )
        return value

    def validate(self, data):
        if data["password"] != data["confirm_password"]:
            raise serializers.ValidationError({
                "confirm_password": "Passwords do not match."
            })
        return data

    @transaction.atomic
    def create(self, validated_data):
        validated_data.pop("confirm_password")
        password = validated_data.pop("password")
        user = User.objects.create_user(
            password=password,
            **validated_data,
        )
        # accounts.signals creates a CUSTOMER UserProfile automatically.
        return user


class LogoutSerializer(serializers.Serializer):
    refresh = serializers.CharField(write_only=True)

    def validate(self, attrs):
        try:
            token = RefreshToken(attrs["refresh"])
        except TokenError:
            raise serializers.ValidationError({
                "refresh": "Invalid or expired refresh token."
            })

        request_user = self.context["request"].user
        if str(token["user_id"]) != str(request_user.pk):
            raise serializers.ValidationError({
                "refresh": "This refresh token does not belong to this user."
            })

        attrs["token"] = token
        return attrs

    def create(self, validated_data):
        validated_data["token"].blacklist()
        return {"message": "Successfully logged out."}


class UserProfileSerializer(serializers.ModelSerializer):
    username = serializers.CharField(source="user.username", read_only=True)
    first_name = serializers.CharField(source="user.first_name", read_only=True)
    last_name = serializers.CharField(source="user.last_name", read_only=True)
    email = serializers.EmailField(source="user.email", read_only=True)

    class Meta:
        model = UserProfile
        fields = [
            "id",
            "username",
            "first_name",
            "last_name",
            "email",
            "role",
            "phone_number",
            "profile_picture",
            "created_at",
        ]
        read_only_fields = [
            "id",
            "username",
            "first_name",
            "last_name",
            "email",
            "role",
            "created_at",
        ]


class UserRoleUpdateSerializer(serializers.ModelSerializer):
    class Meta:
        model = UserProfile
        fields = ["role"]


class ForgotPasswordSerializer(serializers.Serializer):
    email = serializers.EmailField()

    def validate_email(self, value):
        value = value.strip().lower()
        self.user = User.objects.filter(email__iexact=value).first()
        return value

    def save(self):
        # Keep the API response identical for existing and unknown accounts.
        if not self.user:
            return {"sent": False}

        uid = urlsafe_base64_encode(force_bytes(self.user.pk))
        token = default_token_generator.make_token(self.user)

        message = (
            f"Hello {self.user.first_name or self.user.username},\n\n"
            "We received a request to reset your password.\n"
            "Submit the following values to POST /api/accounts/reset-password/:\n\n"
            f"UID: {uid}\n"
            f"Token: {token}\n\n"
            "If you did not request this change, you can ignore this email."
        )

        send_mail(
            subject="AI Ticket Management System - Password reset",
            message=message,
            from_email=None,
            recipient_list=[self.user.email],
            fail_silently=False,
        )
        return {"sent": True}


class ResetPasswordSerializer(serializers.Serializer):
    uid = serializers.CharField()
    token = serializers.CharField()
    new_password = serializers.CharField(
        write_only=True,
        validators=[validate_password],
    )
    confirm_password = serializers.CharField(write_only=True)

    def validate(self, data):
        if data["new_password"] != data["confirm_password"]:
            raise serializers.ValidationError({
                "confirm_password": "Passwords do not match."
            })

        try:
            uid = force_str(urlsafe_base64_decode(data["uid"]))
            user = User.objects.get(pk=uid)
        except (
            binascii.Error,
            TypeError,
            ValueError,
            OverflowError,
            UnicodeDecodeError,
            User.DoesNotExist,
        ):
            raise serializers.ValidationError({
                "uid": "Invalid user ID."
            })

        if not default_token_generator.check_token(user, data["token"]):
            raise serializers.ValidationError({
                "token": "Invalid or expired password reset token."
            })

        self.user = user
        return data

    def save(self):
        self.user.set_password(self.validated_data["new_password"])
        self.user.save(update_fields=["password"])
        return self.user


class GoogleTokenSerializer(serializers.Serializer):
    id_token = serializers.CharField(write_only=True)

    def validate(self, attrs):
        client_id = config("GOOGLE_CLIENT_ID", default="")
        if not client_id:
            raise serializers.ValidationError({
                "detail": "Google sign-in is not configured on this server."
            })

        try:
            claims = id_token.verify_oauth2_token(
                attrs["id_token"],
                google_requests.Request(),
                client_id,
            )
        except ValueError:
            raise serializers.ValidationError({
                "id_token": "Invalid or expired Google ID token."
            })

        if claims.get("email_verified") is not True:
            raise serializers.ValidationError({
                "id_token": "Google email must be verified."
            })

        if not claims.get("sub") or not claims.get("email"):
            raise serializers.ValidationError({
                "id_token": "Google token is missing required account details."
            })

        self.google_claims = claims
        return attrs


class GoogleLoginSerializer(GoogleTokenSerializer):
    @transaction.atomic
    def create(self, validated_data):
        claims = self.google_claims
        google_sub = claims["sub"]
        email = claims["email"].strip().lower()

        identity = (
            GoogleIdentity.objects.select_related("user")
            .filter(google_sub=google_sub)
            .first()
        )

        if identity:
            user = identity.user
        else:
            # Never sign into an existing password account merely because
            # the Google token contains the same email address.
            if User.objects.filter(email__iexact=email).exists():
                raise serializers.ValidationError({
                    "email": (
                        "An account with this email already exists. Sign in "
                        "using that account first, then link Google from the "
                        "authenticated account."
                    )
                })

            username_hash = hashlib.sha256(
                google_sub.encode("utf-8")
            ).hexdigest()[:40]
            username = f"google_{username_hash}"

            try:
                # The savepoint lets us handle a concurrent duplicate safely.
                with transaction.atomic():
                    user = User.objects.create_user(
                        username=username,
                        email=email,
                        first_name=claims.get("given_name", ""),
                        last_name=claims.get("family_name", ""),
                        password=None,
                    )
                    GoogleIdentity.objects.create(
                        user=user,
                        google_sub=google_sub,
                        email=email,
                    )
            except IntegrityError:
                identity = (
                    GoogleIdentity.objects.select_related("user")
                    .filter(google_sub=google_sub)
                    .first()
                )
                if identity is None:
                    raise serializers.ValidationError({
                        "detail": "This Google account could not be linked. Please retry."
                    })
                user = identity.user

        if not user.is_active:
            raise serializers.ValidationError({
                "detail": "This account is inactive."
            })

        refresh = RefreshToken.for_user(user)
        return {
            "message": "Google login successful.",
            "access": str(refresh.access_token),
            "refresh": str(refresh),
        }


class GoogleLinkSerializer(GoogleTokenSerializer):
    @transaction.atomic
    def create(self, validated_data):
        user = self.context["request"].user
        claims = self.google_claims
        google_sub = claims["sub"]
        email = claims["email"].strip().lower()

        if email != (user.email or "").strip().lower():
            raise serializers.ValidationError({
                "email": (
                    "The verified Google email must match the email on "
                    "your signed-in account."
                )
            })

        existing_identity = (
            GoogleIdentity.objects.select_related("user")
            .filter(google_sub=google_sub)
            .first()
        )
        if existing_identity:
            if existing_identity.user_id == user.pk:
                return existing_identity
            raise serializers.ValidationError({
                "id_token": "This Google account is already linked to another user."
            })

        if GoogleIdentity.objects.filter(user=user).exists():
            raise serializers.ValidationError({
                "detail": "A Google account is already linked to this user."
            })

        try:
            with transaction.atomic():
                return GoogleIdentity.objects.create(
                    user=user,
                    google_sub=google_sub,
                    email=email,
                )
        except IntegrityError:
            raise serializers.ValidationError({
                "detail": "This Google account could not be linked. Please retry."
            })
