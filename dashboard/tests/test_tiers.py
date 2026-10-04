"""The membership catalogue: tiers and the perks they list."""

import datetime
import json
from decimal import Decimal

from audience.models import (
    Member,
    MembershipBenefit,
    MembershipTerm,
    MembershipTier,
)
from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

User = get_user_model()


def tier_payload(**overrides) -> dict:
    payload = {
        "name": "Matinee Club",
        "slug": "matinee-club",
        "eyebrow": "",
        "price": "45",
        "duration_months": "12",
        "free_admissions_per_month": "1",
        "checkout_url": "https://square.link/u/matinee",
        "featured": "",
        "is_family_tier": "",
        "show_on_membership_page": "on",
        "sort_order": "5",
        "description": "",
    }
    payload.update(overrides)
    return payload


class StaffOnlyTests(TestCase):
    """Tier pricing and perks are staff business, like the rest of /dashboard."""

    def test_every_catalogue_url_requires_staff(self) -> None:
        tier = MembershipTier.objects.get(slug="individual")
        benefit = MembershipBenefit.objects.first()
        gets = [
            reverse("dashboard:tiers"),
            reverse("dashboard:tier_create"),
            reverse("dashboard:tier_edit", args=[tier.pk]),
            reverse("dashboard:benefit_create"),
            reverse("dashboard:benefit_edit", args=[benefit.pk]),
        ]
        posts = [
            reverse("dashboard:tier_listing", args=[tier.pk]),
            reverse("dashboard:tier_delete", args=[tier.pk]),
            reverse("dashboard:benefit_delete", args=[benefit.pk]),
        ]
        for url in gets:
            with self.subTest(url=url):
                self.assertEqual(self.client.get(url).status_code, 302)
        for url in posts:
            with self.subTest(url=url):
                self.assertEqual(self.client.post(url).status_code, 302)


class StaffTestCase(TestCase):
    def setUp(self) -> None:
        User.objects.create_user(username="s", password="pw12345", is_staff=True)
        self.client.login(username="s", password="pw12345")


class TierListTests(StaffTestCase):
    def test_lists_the_seeded_catalogue_with_prices(self) -> None:
        html = self.client.get(reverse("dashboard:tiers")).content.decode()
        self.assertIn("Individual", html)
        self.assertIn("cinema-supporter", html)

    def test_shows_how_many_terms_point_at_a_tier(self) -> None:
        tier = MembershipTier.objects.get(slug="individual")
        member = Member.objects.create(
            first_name="Ada", last_name="Lovelace", email="ada@example.com"
        )
        MembershipTerm.objects.create(
            member=member, tier=tier,
            started_on=datetime.date(2026, 1, 1),
            expires_on=datetime.date(2026, 12, 31),
            price_paid=Decimal("60.00"),
        )
        html = self.client.get(reverse("dashboard:tiers")).content.decode()
        self.assertIn(f"{reverse('dashboard:terms')}?tier=individual", html)

    def test_a_tier_with_terms_offers_no_delete_button(self) -> None:
        """Deleting it is impossible (PROTECT), so the button would only
        ever produce an error toast."""
        tier = MembershipTier.objects.get(slug="individual")
        member = Member.objects.create(
            first_name="Ada", last_name="Lovelace", email="ada@example.com"
        )
        MembershipTerm.objects.create(
            member=member, tier=tier,
            started_on=datetime.date(2026, 1, 1),
            expires_on=datetime.date(2026, 12, 31),
            price_paid=Decimal("60.00"),
        )
        html = self.client.get(reverse("dashboard:tiers")).content.decode()
        self.assertNotIn(reverse("dashboard:tier_delete", args=[tier.pk]), html)
        self.assertIn(reverse("dashboard:tier_listing", args=[tier.pk]), html)


class CatalogueOrderTests(StaffTestCase):
    """Both lists follow sort_order, as the public page does.

    Their annotations add a GROUP BY, which drops `Meta.ordering`.
    """

    def test_tiers_follow_sort_order(self) -> None:
        # Created last and priced highest: only sort_order puts it first.
        MembershipTier.objects.create(
            slug="patron",
            name="Patron",
            price=999,
            sort_order=1,
            checkout_url="https://square.link/u/patron",
        )
        resp = self.client.get(reverse("dashboard:tiers"))
        self.assertEqual(
            [t.slug for t in resp.context["tiers"]],
            [
                "patron",
                "silver-screen",
                "individual",
                "cinema-supporter",
                "family",
                "family-plus",
            ],
        )

    def test_benefits_follow_sort_order_then_name(self) -> None:
        MembershipBenefit.objects.create(name="Zzz first anyway", sort_order=1)
        resp = self.client.get(reverse("dashboard:tiers"))
        self.assertEqual(
            [b.name for b in resp.context["benefits"]],
            [b.name for b in MembershipBenefit.objects.order_by("sort_order", "name")],
        )
        self.assertEqual(resp.context["benefits"][0].name, "Zzz first anyway")


class TierCreateTests(StaffTestCase):
    def test_creates_a_tier(self) -> None:
        resp = self.client.post(reverse("dashboard:tier_create"), tier_payload())
        self.assertEqual(resp.status_code, 200)
        tier = MembershipTier.objects.get(slug="matinee-club")
        self.assertEqual(tier.price, 45)
        self.assertEqual(tier.free_admissions_per_month, 1)
        self.assertTrue(tier.show_on_membership_page)

    def test_a_new_tier_is_immediately_sellable(self) -> None:
        """The whole point of the page: a tier added here shows up in the
        dropdown for a new membership term without a trip to /admin/."""
        from dashboard.forms import MembershipTermForm

        self.client.post(reverse("dashboard:tier_create"), tier_payload())
        slugs = {t.slug for t in MembershipTermForm().fields["tier"].queryset}
        self.assertIn("matinee-club", slugs)

    def test_perks_can_be_attached_at_creation(self) -> None:
        benefits = list(MembershipBenefit.objects.all()[:2])
        self.client.post(
            reverse("dashboard:tier_create"),
            tier_payload(benefits=[b.pk for b in benefits]),
        )
        tier = MembershipTier.objects.get(slug="matinee-club")
        self.assertEqual(set(tier.benefits.all()), set(benefits))

    def test_duplicate_slug_redisplays_the_form(self) -> None:
        resp = self.client.post(
            reverse("dashboard:tier_create"), tier_payload(slug="individual")
        )
        self.assertEqual(resp.status_code, 200)
        self.assertIn("tier-form", resp.content.decode())
        self.assertNotIn("close-drawer", resp.headers.get("HX-Trigger", ""))

    def test_success_closes_the_drawer_and_toasts(self) -> None:
        resp = self.client.post(reverse("dashboard:tier_create"), tier_payload())
        trigger = json.loads(resp.headers["HX-Trigger"])
        self.assertTrue(trigger["close-drawer"])
        self.assertEqual(trigger["dashboard-toast"]["kind"], "success")

    def test_a_listed_tier_needs_a_payment_link(self) -> None:
        """Otherwise the public card's Join button goes nowhere."""
        resp = self.client.post(
            reverse("dashboard:tier_create"), tier_payload(checkout_url="")
        )
        self.assertEqual(resp.status_code, 200)
        self.assertIn("checkout_url", resp.context["form"].errors)
        self.assertIn("needs its Square payment link", resp.content.decode())
        self.assertFalse(MembershipTier.objects.filter(slug="matinee-club").exists())

    def test_an_unlisted_tier_can_wait_for_its_payment_link(self) -> None:
        payload = tier_payload(checkout_url="")
        del payload["show_on_membership_page"]
        self.client.post(reverse("dashboard:tier_create"), payload)
        self.assertTrue(MembershipTier.objects.filter(slug="matinee-club").exists())

    def test_duration_input_keeps_a_minimum_of_one_month(self) -> None:
        html = self.client.get(reverse("dashboard:tier_create")).content.decode()
        start = html.index('name="duration_months"')
        tag = html[html.rindex("<input", 0, start) : html.index(">", start)]
        self.assertIn('min="1"', tag)

    def test_zero_month_tier_is_refused(self) -> None:
        resp = self.client.post(
            reverse("dashboard:tier_create"), tier_payload(duration_months="0")
        )
        self.assertIn("duration_months", resp.context["form"].errors)
        self.assertFalse(MembershipTier.objects.filter(slug="matinee-club").exists())


class TierEditTests(StaffTestCase):
    def setUp(self) -> None:
        super().setUp()
        self.tier = MembershipTier.objects.get(slug="individual")

    def test_price_change_does_not_touch_past_terms(self) -> None:
        """price_paid is stored on the term precisely so a price rise leaves
        last year's revenue alone."""
        member = Member.objects.create(
            first_name="Ada", last_name="Lovelace", email="ada@example.com"
        )
        term = MembershipTerm.objects.create(
            member=member, tier=self.tier,
            started_on=datetime.date(2025, 1, 1),
            expires_on=datetime.date(2025, 12, 31),
            price_paid=Decimal("60.00"),
        )
        self.client.post(
            reverse("dashboard:tier_edit", args=[self.tier.pk]),
            tier_payload(name=self.tier.name, slug=self.tier.slug, price="75"),
        )
        self.tier.refresh_from_db()
        term.refresh_from_db()
        self.assertEqual(self.tier.price, 75)
        self.assertEqual(term.price_paid, Decimal("60.00"))

    def test_slug_cannot_be_changed_after_creation(self) -> None:
        """Square redirects to /thanks?tier=<slug> and GA4 keys off it, so a
        posted slug is ignored rather than silently breaking attribution."""
        self.client.post(
            reverse("dashboard:tier_edit", args=[self.tier.pk]),
            tier_payload(name="Individual", slug="something-else", price="60"),
        )
        self.tier.refresh_from_db()
        self.assertEqual(self.tier.slug, "individual")

    def test_slug_field_renders_disabled(self) -> None:
        html = self.client.get(
            reverse("dashboard:tier_edit", args=[self.tier.pk])
        ).content.decode()
        self.assertIn("disabled", html)


class TierListingTests(StaffTestCase):
    def setUp(self) -> None:
        super().setUp()
        self.tier = MembershipTier.objects.get(slug="family-plus")

    def test_retire_hides_the_tier_without_deleting_it(self) -> None:
        self.client.post(reverse("dashboard:tier_listing", args=[self.tier.pk]))
        self.tier.refresh_from_db()
        self.assertFalse(self.tier.show_on_membership_page)
        self.assertTrue(MembershipTier.objects.filter(pk=self.tier.pk).exists())

    def test_retiring_stamps_updated_at(self) -> None:
        """It changes the public page, so the sitemap must see it."""
        self.assertIsNone(self.tier.updated_at)  # seeded before the field
        self.client.post(reverse("dashboard:tier_listing", args=[self.tier.pk]))
        self.tier.refresh_from_db()
        self.assertIsNotNone(self.tier.updated_at)

    def test_retire_then_restore_round_trips(self) -> None:
        url = reverse("dashboard:tier_listing", args=[self.tier.pk])
        self.client.post(url)
        self.client.post(url)
        self.tier.refresh_from_db()
        self.assertTrue(self.tier.show_on_membership_page)

    def test_retiring_leaves_the_drawer_alone(self) -> None:
        """It is a row-level toggle, not a form — closing a drawer that was
        never opened would be noise."""
        resp = self.client.post(
            reverse("dashboard:tier_listing", args=[self.tier.pk])
        )
        self.assertNotIn("close-drawer", resp.headers["HX-Trigger"])

    def test_a_tier_without_a_payment_link_cannot_be_restored(self) -> None:
        """Restoring would list a card whose Join button goes nowhere."""
        tier = MembershipTier.objects.create(
            slug="draft", name="Draft", price=10, show_on_membership_page=False
        )
        resp = self.client.post(reverse("dashboard:tier_listing", args=[tier.pk]))
        tier.refresh_from_db()
        self.assertFalse(tier.show_on_membership_page)
        trigger = json.loads(resp.headers["HX-Trigger"])
        self.assertEqual(trigger["dashboard-toast"]["kind"], "error")


class TierDeleteTests(StaffTestCase):
    def test_deletes_a_tier_nobody_bought(self) -> None:
        tier = MembershipTier.objects.create(
            slug="typo", name="Typo", price=1, duration_months=12
        )
        self.client.post(reverse("dashboard:tier_delete", args=[tier.pk]))
        self.assertFalse(MembershipTier.objects.filter(pk=tier.pk).exists())

    def test_a_tier_with_terms_is_refused_and_points_at_retiring(self) -> None:
        tier = MembershipTier.objects.get(slug="individual")
        member = Member.objects.create(
            first_name="Ada", last_name="Lovelace", email="ada@example.com"
        )
        MembershipTerm.objects.create(
            member=member, tier=tier,
            started_on=datetime.date(2026, 1, 1),
            expires_on=datetime.date(2026, 12, 31),
            price_paid=Decimal("60.00"),
        )
        resp = self.client.post(reverse("dashboard:tier_delete", args=[tier.pk]))
        self.assertTrue(MembershipTier.objects.filter(pk=tier.pk).exists())
        toast = json.loads(resp.headers["HX-Trigger"])["dashboard-toast"]
        self.assertEqual(toast["kind"], "error")
        self.assertIn("Retire it instead", toast["message"])


class BenefitTests(StaffTestCase):
    def test_creates_a_perk(self) -> None:
        self.client.post(
            reverse("dashboard:benefit_create"),
            {"name": "Free birthday ticket", "description": "", "sort_order": "9"},
        )
        self.assertTrue(
            MembershipBenefit.objects.filter(name="Free birthday ticket").exists()
        )

    def test_editing_a_perk_updates_every_tier_that_lists_it(self) -> None:
        """Perks are shared rows, so the tier table has to re-render too."""
        benefit = MembershipBenefit.objects.first()
        tier = MembershipTier.objects.get(slug="individual")
        tier.benefits.add(benefit)

        resp = self.client.post(
            reverse("dashboard:benefit_edit", args=[benefit.pk]),
            {"name": "Reworded perk", "description": "", "sort_order": "1"},
        )
        html = resp.content.decode()
        self.assertIn('id="tier-list" hx-swap-oob="true"', html)
        self.assertIn('id="benefit-list" hx-swap-oob="true"', html)
        self.assertIn("Reworded perk", html)

    def test_deleting_a_perk_drops_it_from_tiers_but_keeps_them(self) -> None:
        """benefits is a ManyToMany, so this is not a protected delete — the
        perk goes and the tiers that listed it survive, one perk shorter."""
        tier = MembershipTier.objects.get(slug="individual")
        doomed = MembershipBenefit.objects.create(name="Doomed perk", sort_order=99)
        tier.benefits.add(doomed)
        survivors = set(tier.benefits.exclude(pk=doomed.pk))
        self.assertTrue(survivors, "seeded tier should already carry perks")

        self.client.post(reverse("dashboard:benefit_delete", args=[doomed.pk]))
        self.assertFalse(MembershipBenefit.objects.filter(pk=doomed.pk).exists())
        self.assertTrue(MembershipTier.objects.filter(pk=tier.pk).exists())
        self.assertEqual(set(tier.benefits.all()), survivors)
