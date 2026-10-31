"""
Staff sign-in.

The app is same-origin, so it signs in with Django's session cookie
rather than a token. See spec.md section 3.

    GET  /api/v1/auth/session/   who is signed in, and sets the CSRF cookie
    POST /api/v1/auth/login/     public, rate limited
    POST /api/v1/auth/logout/
    GET  /api/v1/staff/          current staff, for choosing an owner
"""

from django.contrib.auth import authenticate, get_user_model, login, logout
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import csrf_protect, ensure_csrf_cookie
from rest_framework import serializers, status
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.throttling import AnonRateThrottle
from rest_framework.views import APIView

from apps.surveys.models import can_approve_surveys


class LoginThrottle(AnonRateThrottle):
    """Slows password guessing. The rate lives in settings."""

    scope = "login"


class LoginSerializer(serializers.Serializer):
    username = serializers.CharField()
    password = serializers.CharField(trim_whitespace=False)


def describe_staff(user):
    """
    What the frontend knows about the signed-in person.

    Used only to shape the screens. The backend still checks every
    action, so changing this in a browser grants nothing.
    """
    return {
        "id": user.id,
        "name": user.get_full_name() or user.username,
        "roles": user.roles,
        "is_administrator": user.is_superuser or "administrator" in user.roles,
        "can_approve_surveys": can_approve_surveys(user),
    }


@method_decorator(ensure_csrf_cookie, name="dispatch")
class SessionView(APIView):
    """Reports who is signed in. A signed-out visitor gets user: null."""

    permission_classes = [AllowAny]

    def get(self, request):
        user = request.user
        return Response({"user": describe_staff(user) if user.is_authenticated else None})


@method_decorator(csrf_protect, name="dispatch")
class LoginView(APIView):
    """
    Starts a staff session.

    DRF skips CSRF for anonymous requests, so it is switched on here by
    hand. Without it another site could sign a visitor into an account
    of its choosing. No authentication classes, so an expired session
    cookie cannot get in the way of signing in again.
    """

    authentication_classes = []
    permission_classes = [AllowAny]
    throttle_classes = [LoginThrottle]

    def post(self, request):
        serializer = LoginSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        user = authenticate(request._request, **serializer.validated_data)

        # The same message for every failure, so this endpoint cannot be
        # used to discover which usernames exist.
        if user is None or not user.is_active_staff:
            return Response(
                {"detail": "Incorrect username or password."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        login(request._request, user)
        return Response({"user": describe_staff(user)})


class LogoutView(APIView):
    """Ends the session."""

    permission_classes = [IsAuthenticated]

    def post(self, request):
        logout(request._request)
        return Response(status=status.HTTP_204_NO_CONTENT)


class StaffListView(APIView):
    """
    Everyone who can be given work.

    A short list used to fill a picker, so it is not paginated. Holds
    names only: no contact details, and nothing about roles.
    """

    permission_classes = [IsAuthenticated]

    def get(self, request):
        staff = get_user_model().objects.filter(
            is_active=True, is_active_staff=True
        ).order_by("first_name", "last_name", "id")

        return Response(
            [{"id": user.id, "name": user.get_full_name() or user.username} for user in staff]
        )
