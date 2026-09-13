"""Guard the one field editing must never silently break: the tier slug.

Square's payment dashboard redirects to /thanks?tier=<slug> and the Join
button's GA4 tracking carries the same slug. Both are revenue attribution,
not display — the page keeps rendering perfectly if the slug is edited out
from under them. This test pins MembershipTierAdmin.get_readonly_fields
directly so that guarantee doesn't rest on a comment.
"""

from django.test import TestCase

from audience.admin import MembershipTierAdmin
from audience.models import MembershipTier


class MembershipTierAdminReadonlyFieldsTests(TestCase):
    def setUp(self) -> None:
        self.admin = MembershipTierAdmin(MembershipTier, None)

    def test_slug_is_readonly_for_an_existing_tier(self) -> None:
        tier = MembershipTier.objects.get(slug="individual")
        self.assertEqual(
            self.admin.get_readonly_fields(request=None, obj=tier), ("slug",)
        )

    def test_slug_is_editable_when_adding_a_new_tier(self) -> None:
        self.assertEqual(
            self.admin.get_readonly_fields(request=None, obj=None), ()
        )
