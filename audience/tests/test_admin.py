"""Guard the one field editing must never silently break: the tier slug.

Square's payment dashboard redirects to /thanks?tier=<slug> and the Join
button's GA4 tracking carries the same slug. Both are revenue attribution,
not display — the page keeps rendering perfectly if the slug is edited out
from under them. This test pins MembershipTierAdmin.get_readonly_fields
directly so that guarantee doesn't rest on a comment.
"""

import datetime
from decimal import Decimal

from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse

from audience.admin import MembershipTierAdmin
from audience.models import (
    Member,
    MembershipBenefit,
    MembershipTerm,
    MembershipTier,
)


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


class MembershipTierAdminPageTests(TestCase):
    """The admin pages have to actually render.

    The tests above call get_readonly_fields in isolation and pass, which
    is exactly why they did not catch a KeyError raised while building the
    change form: prepopulated_fields still named `slug` after
    get_readonly_fields had removed it from the form. Assert on the
    rendered page, not on the method that feeds it.
    """

    def setUp(self) -> None:
        User.objects.create_superuser(
            username="root", email="root@example.com", password="pw12345"
        )
        self.client.login(username="root", password="pw12345")
        self.tier = MembershipTier.objects.get(slug="individual")

    def change_url(self) -> str:
        return reverse("admin:audience_membershiptier_change", args=[self.tier.pk])

    def test_change_page_renders(self) -> None:
        self.assertEqual(self.client.get(self.change_url()).status_code, 200)

    def test_add_page_renders(self) -> None:
        url = reverse("admin:audience_membershiptier_add")
        self.assertEqual(self.client.get(url).status_code, 200)

    def test_slug_is_shown_but_not_editable_when_changing(self) -> None:
        html = self.client.get(self.change_url()).content.decode()
        self.assertNotIn('name="slug"', html)
        self.assertIn("individual", html)

    def test_slug_is_editable_when_adding(self) -> None:
        url = reverse("admin:audience_membershiptier_add")
        self.assertIn('name="slug"', self.client.get(url).content.decode())


class AudienceAdminSmokeTests(TestCase):
    """Every audience admin page this refactor touched must render.

    The tier catalogue change reached four admin screens: two new models,
    and MemberAdmin's inline, whose `tier` column became a foreign key.
    A 500 on any of them is invisible to the rest of the suite, which
    never asks the admin for a page.
    """

    def setUp(self) -> None:
        User.objects.create_superuser(
            username="root", email="root@example.com", password="pw12345"
        )
        self.client.login(username="root", password="pw12345")

    def assertRenders(self, url_name, *args) -> None:
        url = reverse(url_name, args=args)
        self.assertEqual(self.client.get(url).status_code, 200, url)

    def test_tier_pages(self) -> None:
        tier = MembershipTier.objects.get(slug="individual")
        self.assertRenders("admin:audience_membershiptier_changelist")
        self.assertRenders("admin:audience_membershiptier_add")
        self.assertRenders("admin:audience_membershiptier_change", tier.pk)

    def test_benefit_pages(self) -> None:
        benefit = MembershipBenefit.objects.first()
        self.assertRenders("admin:audience_membershipbenefit_changelist")
        self.assertRenders("admin:audience_membershipbenefit_add")
        self.assertRenders("admin:audience_membershipbenefit_change", benefit.pk)

    def test_member_page_renders_its_term_inline(self) -> None:
        """The inline's tier column is a foreign key now."""
        member = Member.objects.create(
            first_name="Solange", last_name="Pelletier", email="s.p@example.com"
        )
        MembershipTerm.objects.create(
            member=member,
            tier=MembershipTier.objects.get(slug="cinema-supporter"),
            started_on=datetime.date(2026, 1, 1),
            expires_on=datetime.date(2026, 12, 31),
            price_paid=Decimal("120.00"),
        )
        self.assertRenders("admin:audience_member_changelist")
        self.assertRenders("admin:audience_member_change", member.pk)
