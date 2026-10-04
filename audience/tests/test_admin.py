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
    FreeAdmission,
    Member,
    MembershipBenefit,
    MembershipTerm,
    MembershipTier,
    Subscriber,
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

    def test_free_admission_pages(self) -> None:
        member = Member.objects.create(
            first_name="Denis", last_name="Bouchard", email="d.b@example.com"
        )
        admission = FreeAdmission.objects.create(member=member)
        self.assertRenders("admin:audience_freeadmission_changelist")
        self.assertRenders("admin:audience_freeadmission_add")
        self.assertRenders("admin:audience_freeadmission_change", admission.pk)


class MembershipTierAdminValidationTests(TestCase):
    def setUp(self) -> None:
        User.objects.create_superuser(
            username="root", email="root@example.com", password="pw12345"
        )
        self.client.login(username="root", password="pw12345")

    def payload(self, **overrides: str) -> dict:
        return {
            "name": "Matinee Club",
            "slug": "matinee-club",
            "eyebrow": "",
            "description": "",
            "price": "45",
            "duration_months": "12",
            "free_admissions_per_month": "0",
            "checkout_url": "",
            "show_on_membership_page": "on",
            "sort_order": "0",
            **overrides,
        }

    def test_a_listed_tier_needs_a_checkout_link(self) -> None:
        resp = self.client.post(
            reverse("admin:audience_membershiptier_add"), self.payload()
        )
        self.assertEqual(resp.status_code, 200)
        self.assertIn("checkout_url", resp.context["adminform"].form.errors)
        self.assertFalse(MembershipTier.objects.filter(slug="matinee-club").exists())

    def test_a_retired_tier_saves_without_one(self) -> None:
        payload = self.payload()
        del payload["show_on_membership_page"]
        self.client.post(reverse("admin:audience_membershiptier_add"), payload)
        self.assertTrue(MembershipTier.objects.filter(slug="matinee-club").exists())


class EmailCaseAdminTests(TestCase):
    """Emails are stored lowercase, so uniqueness must be judged lowercase.

    The admin's default ModelForms check uniqueness before save() lowercases
    the address, so "ADA@" against a stored "ada@" used to pass the check
    and then hit the unique index: an IntegrityError and a 500.
    """

    def setUp(self) -> None:
        User.objects.create_superuser(
            username="root", email="root@example.com", password="pw12345"
        )
        self.client.login(username="root", password="pw12345")

    def test_member_admin_reports_a_duplicate_in_another_case(self) -> None:
        Member.objects.create(
            first_name="Ada", last_name="Lovelace", email="ada@example.com"
        )
        resp = self.client.post(
            reverse("admin:audience_member_add"),
            {
                "first_name": "Ada",
                "last_name": "Again",
                "email": "ADA@Example.com",
                "phone": "",
                "notes": "",
                "terms-TOTAL_FORMS": "0",
                "terms-INITIAL_FORMS": "0",
                "terms-MIN_NUM_FORMS": "0",
                "terms-MAX_NUM_FORMS": "1000",
            },
        )
        self.assertEqual(resp.status_code, 200)
        self.assertIn("email", resp.context["adminform"].form.errors)
        self.assertEqual(Member.objects.count(), 1)

    def test_subscriber_admin_reports_a_duplicate_in_another_case(self) -> None:
        Subscriber.objects.record("ada@example.com", source="poll_vote")
        resp = self.client.post(
            reverse("admin:audience_subscriber_add"),
            {
                "email": "ADA@Example.com",
                "status": "ACTIVE",
                "source": "admin",
                "consent_ip": "",
                "unsubscribed_at_0": "",
                "unsubscribed_at_1": "",
            },
        )
        self.assertEqual(resp.status_code, 200)
        self.assertIn("email", resp.context["adminform"].form.errors)
        self.assertEqual(Subscriber.objects.count(), 1)

    def test_full_clean_catches_it_for_any_model_form(self) -> None:
        from django.core.exceptions import ValidationError

        Member.objects.create(
            first_name="Ada", last_name="Lovelace", email="ada@example.com"
        )
        member = Member(first_name="Ada", last_name="Again", email="ADA@Example.com")
        with self.assertRaises(ValidationError) as caught:
            member.full_clean()
        self.assertIn("already exists", str(caught.exception.message_dict["email"]))


class MembershipTermInlineQueryTests(TestCase):
    """The inline labels each row with MembershipTerm.__str__, which reads
    the tier — one query per term unless the inline selects it."""

    def test_rows_carry_their_tier(self) -> None:
        from django.contrib.admin.sites import site
        from django.test import RequestFactory

        from audience.admin import MembershipTermInline

        member = Member.objects.create(
            first_name="Solange", last_name="Pelletier", email="s.p@example.com"
        )
        for year in (2024, 2025, 2026):
            MembershipTerm.objects.create(
                member=member,
                tier=MembershipTier.objects.get(slug="individual"),
                started_on=datetime.date(year, 1, 1),
                expires_on=datetime.date(year, 12, 31),
                price_paid=Decimal("60.00"),
            )
        request = RequestFactory().get("/")
        request.user = User.objects.create_superuser(
            username="root", email="root@example.com", password="pw12345"
        )
        terms = list(
            MembershipTermInline(Member, site)
            .get_queryset(request)
            .filter(member=member)
        )
        with self.assertNumQueries(0):
            [str(term) for term in terms]
