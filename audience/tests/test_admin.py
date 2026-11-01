"""The audience admin pages render, and a tier's slug can be edited.

The slug was locked once saved while Square redirected to /thanks?tier=<slug>;
nothing outside this database keys off it since that page went (2026-11-01).
"""

import datetime
from decimal import Decimal

from django.test import TestCase
from django.urls import reverse

from accounts.tests.factories import make_user
from audience.models import (
    FreeAdmission,
    Member,
    MembershipBenefit,
    MembershipTerm,
    MembershipTier,
    Subscriber,
)


class MembershipTierAdminPageTests(TestCase):
    """The admin pages have to actually render: assert on the page, not on
    the methods that feed it."""

    def setUp(self) -> None:
        make_user(
            email="root@example.com",
            password="pw12345",
            is_staff=True,
            is_superuser=True,
        )
        self.client.login(username="root@example.com", password="pw12345")
        self.tier = MembershipTier.objects.get(slug="individual")

    def change_url(self) -> str:
        return reverse("admin:audience_membershiptier_change", args=[self.tier.pk])

    def test_change_page_renders(self) -> None:
        self.assertEqual(self.client.get(self.change_url()).status_code, 200)

    def test_add_page_renders(self) -> None:
        url = reverse("admin:audience_membershiptier_add")
        self.assertEqual(self.client.get(url).status_code, 200)

    def test_slug_is_editable_when_changing(self) -> None:
        html = self.client.get(self.change_url()).content.decode()
        self.assertIn('name="slug"', html)

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
        make_user(
            email="root@example.com",
            password="pw12345",
            is_staff=True,
            is_superuser=True,
        )
        self.client.login(username="root@example.com", password="pw12345")

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
        make_user(
            email="root@example.com",
            password="pw12345",
            is_staff=True,
            is_superuser=True,
        )
        self.client.login(username="root@example.com", password="pw12345")

    def payload(self, **overrides: str) -> dict:
        return {
            "name": "Matinee Club",
            "slug": "matinee-club",
            "eyebrow": "",
            "description": "",
            "price": "45",
            "duration_months": "12",
            "free_admissions_per_month": "0",
            "show_on_membership_page": "on",
            "sort_order": "0",
            **overrides,
        }

    def test_a_listed_tier_saves(self) -> None:
        self.client.post(reverse("admin:audience_membershiptier_add"), self.payload())
        self.assertTrue(MembershipTier.objects.filter(slug="matinee-club").exists())

    def test_a_retired_tier_saves(self) -> None:
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
        make_user(
            email="root@example.com",
            password="pw12345",
            is_staff=True,
            is_superuser=True,
        )
        self.client.login(username="root@example.com", password="pw12345")

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
                "changes-TOTAL_FORMS": "0",
                "changes-INITIAL_FORMS": "0",
                "changes-MIN_NUM_FORMS": "0",
                "changes-MAX_NUM_FORMS": "1000",
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


class SubscriberAdminConsentTests(TestCase):
    """confirmed_at is the CAN-SPAM consent record: staff must not type it."""

    def setUp(self) -> None:
        make_user(
            email="root@example.com",
            password="pw12345",
            is_staff=True,
            is_superuser=True,
        )
        self.client.login(username="root@example.com", password="pw12345")

    def test_admin_created_active_row_has_confirmed_at(self) -> None:
        resp = self.client.post(
            reverse("admin:audience_subscriber_add"),
            {
                "email": "new@example.com",
                "status": "ACTIVE",
                "source": "admin",
                "consent_ip": "",
                "unsubscribed_at_0": "",
                "unsubscribed_at_1": "",
                "changes-TOTAL_FORMS": "0",
                "changes-INITIAL_FORMS": "0",
                "changes-MIN_NUM_FORMS": "0",
                "changes-MAX_NUM_FORMS": "1000",
            },
        )
        self.assertEqual(resp.status_code, 302)
        sub = Subscriber.objects.get(email="new@example.com")
        self.assertIsNotNone(sub.confirmed_at)

    def test_update_fields_save_persists_the_stamp(self) -> None:
        sub, _ = Subscriber.objects.record("ada@example.com", source="poll_vote")
        Subscriber.objects.filter(pk=sub.pk).update(confirmed_at=None)
        sub.refresh_from_db()
        sub.source = "admin"
        sub.save(update_fields=["source"])
        sub.refresh_from_db()
        self.assertIsNotNone(sub.confirmed_at)

    def test_change_form_shows_both_fields_read_only(self) -> None:
        sub, _ = Subscriber.objects.record("ada@example.com", source="poll_vote")
        resp = self.client.get(
            reverse("admin:audience_subscriber_change", args=[sub.pk])
        )
        self.assertEqual(resp.status_code, 200)
        form = resp.context["adminform"].form
        self.assertNotIn("confirmed_at", form.fields)
        self.assertNotIn("confirmation_sent_at", form.fields)
        self.assertContains(resp, "field-confirmed_at")
        self.assertContains(resp, "field-confirmation_sent_at")


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
        request.user = make_user(
            email="root@example.com",
            password="pw12345",
            is_staff=True,
            is_superuser=True,
        )
        terms = list(
            MembershipTermInline(Member, site)
            .get_queryset(request)
            .filter(member=member)
        )
        with self.assertNumQueries(0):
            [str(term) for term in terms]


class SubscriptionHistoryAdminTests(TestCase):
    """The opt-in/opt-out history is the consent record: the subscriber's
    admin page shows it but cannot add, edit or delete rows."""

    def setUp(self) -> None:
        make_user(
            email="root@example.com",
            password="pw12345",
            is_staff=True,
            is_superuser=True,
        )
        self.client.login(username="root@example.com", password="pw12345")
        self.sub, _ = Subscriber.objects.record("ada@example.com", source="poll_vote")
        self.url = reverse("admin:audience_subscriber_change", args=[self.sub.pk])

    def payload(self, **extra: str) -> dict:
        change = self.sub.changes.get()
        return {
            "email": "ada@example.com",
            "status": "ACTIVE",
            "source": "poll_vote",
            "consent_ip": "",
            "unsubscribed_at_0": "",
            "unsubscribed_at_1": "",
            "changes-TOTAL_FORMS": "1",
            "changes-INITIAL_FORMS": "1",
            "changes-MIN_NUM_FORMS": "0",
            "changes-MAX_NUM_FORMS": "1000",
            "changes-0-id": str(change.pk),
            "changes-0-subscriber": str(self.sub.pk),
            **extra,
        }

    def test_inline_offers_no_add_and_no_delete(self) -> None:
        resp = self.client.get(self.url)
        [inline] = resp.context["inline_admin_formsets"]
        self.assertFalse(inline.has_add_permission)
        self.assertFalse(inline.formset.can_delete)

    def test_a_posted_delete_keeps_the_row(self) -> None:
        before = list(self.sub.changes.values_list("pk", "status", "at"))
        resp = self.client.post(self.url, self.payload(**{"changes-0-DELETE": "on"}))
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(
            list(self.sub.changes.values_list("pk", "status", "at")), before
        )

    def test_a_posted_new_row_is_not_saved(self) -> None:
        data = self.payload(
            **{
                "changes-TOTAL_FORMS": "2",
                "changes-1-status": "UNSUBSCRIBED",
                "changes-1-at_0": "2026-01-01",
                "changes-1-at_1": "12:00:00",
                "changes-1-subscriber": str(self.sub.pk),
            }
        )
        self.client.post(self.url, data)
        self.assertEqual(self.sub.changes.count(), 1)
