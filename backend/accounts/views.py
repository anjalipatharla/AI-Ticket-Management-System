from django.shortcuts import get_object_or_404
from rest_framework import generics, status
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.views import APIView
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView

from .models import UserProfile
from .permissions import IsApplicationAdmin
from .serializers import (
    EmailOrUsernameTokenObtainPairSerializer,
    ForgotPasswordSerializer,
    GoogleLinkSerializer,
    GoogleLoginSerializer,
    LogoutSerializer,
    RegisterSerializer,
    ResetPasswordSerializer,
    UserProfileSerializer,
    UserRoleUpdateSerializer,
)


class RegisterView(generics.GenericAPIView):
    serializer_class = RegisterSerializer
    permission_classes = [AllowAny]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "register"

    def post(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = serializer.save()
        refresh = RefreshToken.for_user(user)
        profile = user.profile

        return Response(
            {
                "message": "Registration successful.",
                "user": {
                    "id": user.pk,
                    "username": user.username,
                    "first_name": user.first_name,
                    "last_name": user.last_name,
                    "email": user.email,
                    "role": profile.role,
                },
                "access": str(refresh.access_token),
                "refresh": str(refresh),
            },
            status=status.HTTP_201_CREATED,
        )


class LogoutView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        serializer = LogoutSerializer(
            data=request.data,
            context={"request": request},
        )
        serializer.is_valid(raise_exception=True)
        result = serializer.save()
        return Response(result, status=status.HTTP_200_OK)


class UserProfileView(generics.RetrieveUpdateAPIView):
    serializer_class = UserProfileSerializer
    permission_classes = [IsAuthenticated]
    http_method_names = ["get", "patch", "head", "options"]

    def get_object(self):
        return get_object_or_404(
            UserProfile.objects.select_related("user"),
            user=self.request.user,
        )


class ForgotPasswordView(APIView):
    permission_classes = [AllowAny]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "password_reset"

    def post(self, request):
        serializer = ForgotPasswordSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        serializer.save()

        return Response(
            {
                "message": (
                    "If an account exists with this email, "
                    "password reset instructions will be sent."
                )
            },
            status=status.HTTP_200_OK,
        )


class ResetPasswordView(APIView):
    permission_classes = [AllowAny]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "password_reset"

    def post(self, request):
        serializer = ResetPasswordSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        serializer.save()

        return Response(
            {"message": "Password has been reset successfully."},
            status=status.HTTP_200_OK,
        )


class GoogleLoginView(generics.GenericAPIView):
    serializer_class = GoogleLoginSerializer
    permission_classes = [AllowAny]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "google_login"

    def post(self, request):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        return Response(serializer.save(), status=status.HTTP_200_OK)


class GoogleLinkView(generics.GenericAPIView):
    serializer_class = GoogleLinkSerializer
    permission_classes = [IsAuthenticated]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "google_link"

    def post(self, request):
        serializer = self.get_serializer(
            data=request.data,
            context={"request": request},
        )
        serializer.is_valid(raise_exception=True)
        identity = serializer.save()

        return Response(
            {
                "message": "Google account linked successfully.",
                "email": identity.email,
            },
            status=status.HTTP_200_OK,
        )


class UserRoleUpdateView(APIView):
    permission_classes = [IsAuthenticated, IsApplicationAdmin]

    def patch(self, request, user_id):
        if set(request.data.keys()) != {"role"}:
            return Response(
                {"detail": "Submit only the role field."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        profile = get_object_or_404(
            UserProfile.objects.select_related("user"),
            user_id=user_id,
        )
        serializer = UserRoleUpdateSerializer(
            profile,
            data=request.data,
            partial=True,
        )
        serializer.is_valid(raise_exception=True)

        new_role = serializer.validated_data["role"]
        if (
            profile.role == UserProfile.Role.ADMIN
            and new_role != UserProfile.Role.ADMIN
        ):
            active_admin_count = UserProfile.objects.filter(
                role=UserProfile.Role.ADMIN,
                user__is_active=True,
            ).count()
            if active_admin_count <= 1:
                return Response(
                    {"detail": "The last active Application Admin cannot be removed."},
                    status=status.HTTP_400_BAD_REQUEST,
                )

        profile = serializer.save()
        return Response(
            {
                "message": "User role updated successfully.",
                "user_id": profile.user_id,
                "username": profile.user.username,
                "role": profile.role,
            },
            status=status.HTTP_200_OK,
        )


class LoginView(TokenObtainPairView):
    serializer_class = EmailOrUsernameTokenObtainPairSerializer
    permission_classes = [AllowAny]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "login"


class RefreshView(TokenRefreshView):
    permission_classes = [AllowAny]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "token_refresh"
