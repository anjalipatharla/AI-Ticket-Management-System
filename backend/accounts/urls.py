from django.urls import path
from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView

from .views import (
    ForgotPasswordView,
    GoogleLinkView,
    GoogleLoginView,
    LogoutView,
    RegisterView,
    ResetPasswordView,
    UserProfileView,
    UserRoleUpdateView,
)

urlpatterns = [
    path("register/", RegisterView.as_view(), name="register"),
    path("login/", TokenObtainPairView.as_view(), name="token_obtain_pair"),
    path("token/refresh/", TokenRefreshView.as_view(), name="token_refresh"),
    path("logout/", LogoutView.as_view(), name="logout"),
    path("profile/", UserProfileView.as_view(), name="profile"),
    path("forgot-password/", ForgotPasswordView.as_view(), name="forgot_password"),
    path("reset-password/", ResetPasswordView.as_view(), name="reset_password"),
    path("google/", GoogleLoginView.as_view(), name="google_login"),
    path("google/link/", GoogleLinkView.as_view(), name="google_link"),
    path(
        "users/<int:user_id>/role/",
        UserRoleUpdateView.as_view(),
        name="user-role-update",
    ),
]
