from django.urls import path

from .views import (
    AssignApplicationRoleView,
    ForgotPasswordView,
    GoogleIdentityLinkView,
    GoogleLoginView,
    LogoutView,
    RegisterView,
    ResetPasswordView,
    UserProfileView,
)

urlpatterns = [
    path("register/", RegisterView.as_view(), name="register"),
    path("logout/", LogoutView.as_view(), name="logout"),
    path("profile/", UserProfileView.as_view(), name="profile"),
    path(
        "users/<int:pk>/role/",
        AssignApplicationRoleView.as_view(),
        name="assign_application_role",
    ),
    path(
        "google/link/",
        GoogleIdentityLinkView.as_view(),
        name="google_link",
    ),
    path(
        "forgot-password/",
        ForgotPasswordView.as_view(),
        name="forgot_password",
    ),
    path(
        "reset-password/",
        ResetPasswordView.as_view(),
        name="reset_password",
    ),
    path("google/", GoogleLoginView.as_view(), name="google_login"),
]
