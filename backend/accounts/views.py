from django.shortcuts import get_object_or_404

from rest_framework import generics, status
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.tokens import RefreshToken

from .models import UserProfile
from .permissions import IsApplicationAdmin
from .serializers import (
    AssignApplicationRoleSerializer,
    ForgotPasswordSerializer,
    GoogleIdentityLinkSerializer,
    GoogleLoginSerializer,
    LogoutSerializer,
    RegisterSerializer,
    ResetPasswordSerializer,
    UserProfileSerializer,
)


class RegisterView(generics.CreateAPIView):
    serializer_class = RegisterSerializer
    permission_classes = [AllowAny]

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = serializer.save()

        refresh = RefreshToken.for_user(user)
        return Response(
            {
                "message": "Registration successful.",
                "user": UserProfileSerializer(user.profile).data,
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
            context={"request": request}
        )
        serializer.is_valid(raise_exception=True)
        result = serializer.save()
        return Response(result, status=status.HTTP_200_OK)


class UserProfileView(generics.RetrieveUpdateAPIView):
    serializer_class = UserProfileSerializer
    permission_classes = [IsAuthenticated]

    def get_object(self):
        return get_object_or_404(UserProfile, user=self.request.user)


class AssignApplicationRoleView(generics.UpdateAPIView):
    """PATCH /api/accounts/users/<pk>/role/ (application admins only)."""

    serializer_class = AssignApplicationRoleSerializer
    permission_classes = [IsApplicationAdmin]
    queryset = UserProfile.objects.select_related("user").all()


class ForgotPasswordView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        serializer = ForgotPasswordSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        reset_data = serializer.save()

        if reset_data:
            from django.conf import settings
            from django.core.mail import send_mail

            send_mail(
                subject="Password reset request",
                message=(
                    "Use these details in the password reset flow.\n"
                    f"UID: {reset_data['uid']}\n"
                    f"Token: {reset_data['token']}\n"
                ),
                from_email=settings.DEFAULT_FROM_EMAIL,
                recipient_list=[serializer.user.email],
                fail_silently=False,
            )

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

    def post(self, request):
        serializer = ResetPasswordSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(
            {"message": "Password has been reset successfully."},
            status=status.HTTP_200_OK,
        )


class GoogleLoginView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        serializer = GoogleLoginSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        return Response(serializer.save(), status=status.HTTP_200_OK)


class GoogleIdentityLinkView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        serializer = GoogleIdentityLinkSerializer(
            data=request.data,
            context={"request": request},
        )
        serializer.is_valid(raise_exception=True)
        return Response(serializer.save(), status=status.HTTP_200_OK)
