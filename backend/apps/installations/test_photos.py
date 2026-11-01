"""
F11 - who may see a photo of the work.

Photos are evidence of what was fitted on a customer's roof. They live in
private storage, so the only way to see one is through a view that asks
whether this person may see the report it belongs to.
"""

import shutil
import tempfile

from django.contrib.auth import get_user_model
from django.test import override_settings
from django.urls import reverse

from apps.accounts.models import Role
from apps.quotations.test_acceptance import signature_file

from .models import InstallationPhoto
from .tests import InstallationTestCase

User = get_user_model()


class PhotoAccessTests(InstallationTestCase):
    def setUp(self):
        # Uploads go to a folder removed after the test, not the real store.
        media_root = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, media_root, ignore_errors=True)
        override = override_settings(MEDIA_ROOT=media_root)
        override.enable()
        self.addCleanup(override.disable)

        super().setUp()
        self.report = self.open_report()
        self.client.force_login(self.crew)
        self.uploaded = self.client.post(
            reverse("installation-photos", args=[self.report.pk]),
            {"image": signature_file("roof.png"), "caption": "Finished array from the south"},
        ).json()

    def fetch(self, user=None):
        if user is not None:
            self.client.force_login(user)
        return self.client.get(self.uploaded["url"])

    def test_a_photo_comes_with_a_link_not_a_storage_path(self):
        self.assertEqual(self.uploaded["url"],
                         reverse("installation-photo-file", args=[self.uploaded["id"]]))
        self.assertNotIn("image", self.uploaded)

        detail = self.client.get(reverse("installation-detail", args=[self.report.pk])).json()
        self.assertEqual(detail["photos"][0]["url"], self.uploaded["url"])

    def test_the_crew_on_the_job_sees_the_photo_itself(self):
        response = self.fetch(self.crew)

        self.assertEqual(response.status_code, 200)
        stored = InstallationPhoto.objects.get(pk=self.uploaded["id"]).image
        with stored.open("rb") as file:
            self.assertEqual(b"".join(response.streaming_content), file.read())

    def test_the_office_sees_it(self):
        support = User.objects.create_user("photo_support", roles=[Role.SUPPORT])
        for user in (self.ops, support):
            with self.subTest(user=user.username):
                self.assertEqual(self.fetch(user).status_code, 200)

    def test_another_crew_learns_nothing_about_it(self):
        """The same answer as a photo that does not exist."""
        stranger = User.objects.create_user("other_crew", roles=[Role.TECHNICIAN])
        self.assertEqual(self.fetch(stranger).status_code, 404)

    def test_roles_without_installation_access_are_refused(self):
        for user in (self.warehouse, self.finance):
            with self.subTest(user=user.username):
                self.assertEqual(self.fetch(user).status_code, 403)

    def test_a_signed_out_visitor_is_refused(self):
        self.client.logout()
        self.assertEqual(self.fetch().status_code, 403)

    def test_an_unknown_photo_is_a_404(self):
        self.client.force_login(self.ops)
        url = reverse("installation-photo-file", args=[self.uploaded["id"] + 999])
        self.assertEqual(self.client.get(url).status_code, 404)
