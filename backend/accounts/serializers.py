from django.contrib.auth.models import User
from django.contrib.auth.password_validation import validate_password
from django.contrib.auth.tokens import default_token_generator
from django.db import transaction
from django.utils.encoding import force_bytes, force_str
from django.utils.http import urlsafe_base64_decode, urlsafe_base64_encode

from rest_framework import serializers
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework_simplejwt.exceptions import TokenError

from .models import GoogleIdentity, UserProfile

from google.auth.transport import requests as google_requests
from google.oauth2 import id_token
from decouple import config


def verify_google_id_token(raw_token):
    """Verify signature, issuer, expiry and audience through google-auth."""
    try:
        payload = id_token.verify_oauth2_token(
            raw_token,
            google_requests.Request(),
            config("GOOGLE_CLIENT_ID")
        )
    except ValueError:
        raise serializers.ValidationError({
            "id_token": "Invalid Google ID token."
        })

    if not payload.get("email_verified"):
        raise serializers.ValidationError({
            "id_token": "Google email is not verified."
        })
    if not payload.get("sub") or not payload.get("email"):
        raise serializers.ValidationError({
            "id_token": "Required Google account information is missing."
        })
    return payload


class RegisterSerializer(serializers.Serializer):

    username = serializers.CharField(max_length=150)
    first_name = serializers.CharField(max_length=150)
    last_name = serializers.CharField(
        max_length=150,
        required=False,
        allow_blank=True
    )
    email = serializers.EmailField()
    password = serializers.CharField(
        write_only=True,
        validators=[validate_password]
    )
    confirm_password = serializers.CharField(write_only=True)

    def validate_username(self, value):
        if User.objects.filter(username__iexact=value).exists():
            raise serializers.ValidationError(
                "This username is already taken."
            )
        return value

    def validate_email(self, value):
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
        validated_data["email"] = validated_data["email"].strip().lower()
        return User.objects.create_user(password=password, **validated_data)


class LogoutSerializer(serializers.Serializer):

    refresh = serializers.CharField(write_only=True)

    def validate(self, attrs):
        try:
            token = RefreshToken(attrs["refresh"])
            if str(token["user_id"]) != str(self.context["request"].user.pk):
                raise serializers.ValidationError(
                    "This refresh token does not belong to this user."
                )
            attrs["token"] = token
        except TokenError:
            raise serializers.ValidationError(
                "Invalid or expired refresh token."
            )
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
            "id", "username", "first_name", "last_name", "email",
            "role", "phone_number", "profile_picture", "created_at",
        ]
        read_only_fields = [
            "id", "username", "first_name", "last_name", "email",
            "role", "created_at",
        ]


class AssignApplicationRoleSerializer(serializers.ModelSerializer):
    """Application admins can assign operational roles, never ADMIN via API."""

    role = serializers.ChoiceField(
        choices=[
            (UserProfile.Role.CUSTOMER, "Customer"),
            (UserProfile.Role.AGENT, "Support Agent"),
            (UserProfile.Role.MANAGER, "Manager"),
        ]
    )

    class Meta:
        model = UserProfile
        fields = ["role"]


class ForgotPasswordSerializer(serializers.Serializer):

    email = serializers.EmailField()

    def validate_email(self, value):
        self.user = User.objects.filter(email__iexact=value.strip()).first()
        return value

    def save(self):
        if not self.user:
            return None
        uid = urlsafe_base64_encode(force_bytes(self.user.pk))
        token = default_token_generator.make_token(self.user)
        return {"uid": uid, "token": token}


class ResetPasswordSerializer(serializers.Serializer):

    uid = serializers.CharField()
    token = serializers.CharField()
    new_password = serializers.CharField(
        write_only=True,
        validators=[validate_password]
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
        except (TypeError, ValueError, OverflowError, User.DoesNotExist):
            raise serializers.ValidationError({"uid": "Invalid user ID."})

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


class GoogleLoginSerializer(serializers.Serializer):

    id_token = serializers.CharField(write_only=True)

    def validate(self, attrs):
        self.google_user = verify_google_id_token(attrs["id_token"])
        return attrs

    @transaction.atomic
    def create(self, validated_data):
        google_user = self.google_user
        google_sub = google_user["sub"]
        email = google_user["email"].strip().lower()

        identity = (
            GoogleIdentity.objects.select_related("user")
            .filter(google_sub=google_sub)
            .first()
        )
        if identity:
            user = identity.user
            if not user.is_active:
                raise serializers.ValidationError({
                    "detail": "This account is inactive."
                })
        else:
            # Upgrade accounts created by the previous Google login code.
            # That implementation used username google_<sub> and left the
            # password unusable, but did not store a GoogleIdentity row.
            legacy_user = User.objects.filter(
                username=f"google_{google_sub}",
                email__iexact=email,
            ).first()

            if legacy_user and not legacy_user.has_usable_password():
                if not legacy_user.is_active:
                    raise serializers.ValidationError({
                        "detail": "This account is inactive."
                    })
                user = legacy_user
                GoogleIdentity.objects.create(
                    user=user,
                    google_sub=google_sub,
                    email=email,
                )
            else:
                # Never link an ordinary local account merely because its
                # email matches a verified Google email.
                if User.objects.filter(email__iexact=email).exists():
                    raise serializers.ValidationError({
                        "email": (
                            "An account with this email already exists. "
                            "Sign in to that account and use the authenticated "
                            "Google account-linking endpoint."
                        )
                    })

                user = User.objects.create_user(
                    username=f"google_{google_sub}",
                    email=email,
                    first_name=google_user.get("given_name", ""),
                    last_name=google_user.get("family_name", ""),
                )
                GoogleIdentity.objects.create(
                    user=user,
                    google_sub=google_sub,
                    email=email,
                )

        refresh = RefreshToken.for_user(user)
        return {
            "message": "Google login successful.",
            "access": str(refresh.access_token),
            "refresh": str(refresh),
        }


class GoogleIdentityLinkSerializer(serializers.Serializer):

    id_token = serializers.CharField(write_only=True)

    def validate(self, attrs):
        google_user = verify_google_id_token(attrs["id_token"])
        request_user = self.context["request"].user
        google_email = google_user["email"].strip().lower()

        if not request_user.email or request_user.email.lower() != google_email:
            raise serializers.ValidationError({
                "id_token": (
                    "The verified Google email must match the signed-in "
                    "account email before linking."
                )
            })

        linked_identity = GoogleIdentity.objects.filter(
            google_sub=google_user["sub"]
        ).first()
        if linked_identity and linked_identity.user_id != request_user.pk:
            raise serializers.ValidationError({
                "id_token": "This Google account is already linked elsewhere."
            })

        current_identity = GoogleIdentity.objects.filter(
            user=request_user
        ).first()
        if current_identity and current_identity.google_sub != google_user["sub"]:
            raise serializers.ValidationError({
                "id_token": "A different Google account is already linked."
            })

        self.google_user = google_user
        return attrs

    @transaction.atomic
    def create(self, validated_data):
        user = self.context["request"].user
        google_user = self.google_user
        identity, created = GoogleIdentity.objects.get_or_create(
            user=user,
            defaults={
                "google_sub": google_user["sub"],
                "email": google_user["email"].strip().lower(),
            },
        )
        if not created and identity.google_sub != google_user["sub"]:
            raise serializers.ValidationError({
                "id_token": "A different Google account is already linked."
            })
        return {
            "message": (
                "Google account linked successfully."
                if created else "This Google account is already linked."
            )
        }
