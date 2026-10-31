"""URL routes for staff sign-in and the staff list."""

from django.urls import path

from .views import LoginView, LogoutView, SessionView, StaffListView

urlpatterns = [
    path("auth/session/", SessionView.as_view(), name="auth-session"),
    path("auth/login/", LoginView.as_view(), name="auth-login"),
    path("auth/logout/", LogoutView.as_view(), name="auth-logout"),

    # F02
    path("staff/", StaffListView.as_view(), name="staff-list"),
]
