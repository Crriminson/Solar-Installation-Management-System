"""
Tests for staff sign-in.

The rules worth proving: a wrong password and an unknown user look the
same, a leaver cannot sign in, login needs a CSRF token, and repeated
guesses are slowed down whatever a client claims its address is.
"""

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import Client, TestCase
from django.urls import reverse

from .models import Role

User = get_user_model()

PASSWORD = "test-pass-123"


class SessionTests(TestCase):
    def setUp(self):
        cache.clear()
        self.user = User.objects.create_user(
            username="priya", password=PASSWORD, first_name="Priya",
            roles=[Role.SALES],
        )

    def test_a_signed_out_visitor_has_no_user(self):
        response = self.client.get(reverse("auth-session"))

        self.assertEqual(response.status_code, 200)
        self.assertIsNone(response.json()["user"])

    def test_reading_the_session_sets_the_csrf_cookie(self):
        response = self.client.get(reverse("auth-session"))

        self.assertIn("csrftoken", response.cookies)

    def test_correct_password_signs_in(self):
        response = self.client.post(
            reverse("auth-login"), {"username": "priya", "password": PASSWORD}
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["user"]["name"], "Priya")

        session = self.client.get(reverse("auth-session")).json()
        self.assertEqual(session["user"]["roles"], ["sales"])

    def test_wrong_password_and_unknown_user_look_the_same(self):
        wrong = self.client.post(
            reverse("auth-login"), {"username": "priya", "password": "nope"}
        )
        unknown = self.client.post(
            reverse("auth-login"), {"username": "ghost", "password": "nope"}
        )

        self.assertEqual(wrong.status_code, 400)
        self.assertEqual(wrong.json(), unknown.json())

    def test_someone_who_has_left_cannot_sign_in(self):
        self.user.is_active_staff = False
        self.user.save()

        response = self.client.post(
            reverse("auth-login"), {"username": "priya", "password": PASSWORD}
        )

        self.assertEqual(response.status_code, 400)

    def test_logout_ends_the_session(self):
        self.client.login(username="priya", password=PASSWORD)

        response = self.client.post(reverse("auth-logout"))

        self.assertEqual(response.status_code, 204)
        self.assertIsNone(self.client.get(reverse("auth-session")).json()["user"])

    def test_logout_requires_a_session(self):
        response = self.client.post(reverse("auth-logout"))

        self.assertIn(response.status_code, [401, 403])

    def test_login_is_refused_without_a_csrf_token(self):
        client = Client(enforce_csrf_checks=True)

        response = client.post(
            reverse("auth-login"), {"username": "priya", "password": PASSWORD}
        )

        self.assertEqual(response.status_code, 403)


class LoginThrottleTests(TestCase):
    def setUp(self):
        cache.clear()

    def guess(self, **headers):
        return self.client.post(
            reverse("auth-login"),
            {"username": "priya", "password": "guess"},
            **headers,
        ).status_code

    def test_repeated_guesses_are_slowed_down(self):
        codes = [self.guess() for _ in range(11)]

        self.assertEqual(codes[-1], 429)

    def test_a_forged_forwarded_address_does_not_reset_the_limit(self):
        codes = [
            self.guess(HTTP_X_FORWARDED_FOR=f"10.0.0.{attempt}")
            for attempt in range(11)
        ]

        self.assertEqual(codes[-1], 429)


class RoleTests(TestCase):
    def test_a_superuser_holds_every_role(self):
        """Otherwise the first account made on a new install can do nothing."""
        user = User.objects.create_superuser("root", "root@example.com", PASSWORD)

        self.assertTrue(user.has_role(Role.OPERATIONS_MANAGER))

    def test_a_normal_user_holds_only_their_own_roles(self):
        user = User.objects.create_user("tech", password=PASSWORD, roles=[Role.TECHNICIAN])

        self.assertTrue(user.has_role(Role.TECHNICIAN))
        self.assertFalse(user.has_role(Role.OPERATIONS_MANAGER))
