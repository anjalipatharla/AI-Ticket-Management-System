
from django.urls import path

from .views import (
    RegisterView,
    LogoutView,
    UserProfileView,
    ForgotPasswordView,
    ResetPasswordView,
    GoogleLoginView,
)

urlpatterns = [
    path("register/", RegisterView.as_view(), name="register"),
    path("logout/", LogoutView.as_view(), name="logout"),
    path("profile/", UserProfileView.as_view(), name="profile"),
    path("forgot-password/", ForgotPasswordView.as_view(), name="forgot_password"),
    path("reset-password/", ResetPasswordView.as_view(), name="reset_password"),
    path("google/", GoogleLoginView.as_view(), name="google_login"),
]
