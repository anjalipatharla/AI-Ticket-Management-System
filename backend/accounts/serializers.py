from django.contrib.auth.models import User
from django.contrib.auth.password_validation import validate_password
from django.contrib.auth.tokens import default_token_generator
from django.utils.encoding import force_bytes, force_str
from django.utils.http import urlsafe_base64_decode, urlsafe_base64_encode

from rest_framework import serializers
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework_simplejwt.exceptions import TokenError

from .models import UserProfile

from google.auth.transport import requests as google_requests
from google.oauth2 import id_token
from decouple import config


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

    def create(self, validated_data):

        validated_data.pop("confirm_password")

        password = validated_data.pop("password")

        user = User.objects.create_user(
            password=password,
            **validated_data
        )

        return user


class LogoutSerializer(serializers.Serializer):

    refresh = serializers.CharField()

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

    username = serializers.CharField(
        source="user.username",
        read_only=True
    )

    first_name = serializers.CharField(
        source="user.first_name",
        read_only=True
    )

    last_name = serializers.CharField(
        source="user.last_name",
        read_only=True
    )

    email = serializers.EmailField(
        source="user.email",
        read_only=True
    )

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


class ForgotPasswordSerializer(serializers.Serializer):

    email = serializers.EmailField()

    def validate_email(self, value):
        self.user = User.objects.filter(
            email__iexact=value
        ).first()

        return value

    def save(self):
        if not self.user:
            return None

        uid = urlsafe_base64_encode(
            force_bytes(self.user.pk)
        )

        token = default_token_generator.make_token(
            self.user
        )

        return {
            "uid": uid,
            "token": token
        }


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
            uid = force_str(
                urlsafe_base64_decode(data["uid"])
            )

            user = User.objects.get(pk=uid)

        except (TypeError, ValueError, OverflowError, User.DoesNotExist):
            raise serializers.ValidationError({
                "uid": "Invalid user ID."
            })

        if not default_token_generator.check_token(
            user, data["token"]
        ):
            raise serializers.ValidationError({
                "token": "Invalid or expired password reset token."
            })

        self.user = user

        return data

    def save(self):

        self.user.set_password(
            self.validated_data["new_password"]
        )

        self.user.save()

        return self.user


class GoogleLoginSerializer(serializers.Serializer):

    id_token = serializers.CharField()

    def validate(self, attrs):

        google_token = attrs["id_token"]

        try:
            google_user = id_token.verify_oauth2_token(
                google_token,
                google_requests.Request(),
                config("GOOGLE_CLIENT_ID")
            )
        except ValueError as error:
            print("GOOGLE TOKEN ERROR:", repr(error))
            raise serializers.ValidationError({
                "id_token": "Invalid Google ID token."
            })

        if not google_user.get("email_verified"):
            raise serializers.ValidationError({
                "id_token": "Google email is not verified."
            })

        self.google_user = google_user

        return attrs

    def create(self, validated_data):

        google_user = self.google_user

        email = google_user["email"].lower()
        google_id = google_user["sub"]

        user = User.objects.filter(
            email__iexact=email
        ).first()

        if user is None:
            username = f"google_{google_id}"

            user = User.objects.create_user(
                username=username,
                email=email,
                first_name=google_user.get("given_name", ""),
                last_name=google_user.get("family_name", ""),
            )

        refresh = RefreshToken.for_user(user)

        return {
            "message": "Google login successful.",
            "access": str(refresh.access_token),
            "refresh": str(refresh),
        }
