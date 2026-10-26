import datetime
import re
from decimal import Decimal

from accounts.tests.factories import make_user
from audience.models import FreeAdmission, MembershipTerm, MembershipTier
from dashboard.tests.helpers import make_staff
from dashboard.tests.test_free_admissions import (
    give_expired_term,
    give_term,
    make_member,
)
from unittest import mock

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone


class MemberHomeTests(TestCase):
    def sign_in(self, email="m.o@example.com"):
        user = make_user(email, "pw12345", is_staff=False)
        self.client.force_login(user)
        return user

    def test_member_with_roster_match_sees_membership(self) -> None:
        member = make_member(email="m.o@example.com")
        term = give_term(member, "cinema-supporter")
        FreeAdmission.objects.create(member=member)
        self.sign_in()
        resp = self.client.get(reverse("dashboard:home"))
        self.assertTemplateUsed(resp, "dashboard/member_home.html")
        html = resp.content.decode()
        self.assertIn("m.o@example.com", html)
        self.assertIn(term.tier.name, html)
        self.assertIn("Active", html)
        self.assertIn(term.expires_on.strftime("%b %-d, %Y"), html)
        self.assertEqual(resp.context["free_used"], 1)
        self.assertIn(f"1 / {member.free_admission_allowance}", html)

    def test_member_without_match_sees_join_prompt(self) -> None:
        self.sign_in("nobody@example.com")
        resp = self.client.get(reverse("dashboard:home"))
        html = resp.content.decode()
        self.assertIsNone(resp.context["member"])
        self.assertIn(
            "No membership on file for this email. You can join on the "
            "membership page, or at the box office before any show.",
            html,
        )
        self.assertIn('href="/membership/"', html)

    def test_member_sidebar_has_no_staff_links(self) -> None:
        self.sign_in()
        html = self.client.get(reverse("dashboard:home")).content.decode()
        nav = re.search(r'data-cy="sidebar-nav".*?</nav>', html, re.S).group(0)
        labels = [
            re.sub(r"<[^>]+>", "", a).strip()
            for a in re.findall(r"<a .*?</a>", nav, re.S)
        ]
        self.assertEqual(labels, ["Home"])
        self.assertIn("fkc-logo-white.png", html)
        self.assertIn("powered by", html)
        self.assertIn("LeprinceOS", html)
        self.assertIn('data-cy="logout-button"', html)

    def test_member_gets_403_on_staff_pages(self) -> None:
        self.sign_in()
        url = reverse("dashboard:members")
        self.assertEqual(self.client.get(url).status_code, 403)
        self.assertEqual(self.client.get(url, HTTP_HX_REQUEST="true").status_code, 403)

    def test_staff_home_unchanged(self) -> None:
        make_staff(email="s@example.com", password="pw12345")
        self.client.login(username="s@example.com", password="pw12345")
        resp = self.client.get(reverse("dashboard:home"))
        self.assertTemplateUsed(resp, "dashboard/home.html")
        self.assertIn("display_name", resp.context)

    def test_anonymous_redirected_to_login(self) -> None:
        resp = self.client.get(reverse("dashboard:home"))
        self.assertEqual(resp.status_code, 302)
        self.assertIn("/login", resp["Location"])


class MemberHomeStateTests(TestCase):
    sign_in = MemberHomeTests.sign_in

    def page(self) -> str:
        self.sign_in()
        return self.client.get(reverse("dashboard:home")).content.decode()

    def fmt(self, d) -> str:
        return d.strftime("%b %-d, %Y")

    def test_expiring_shows_tier_and_covered_through(self) -> None:
        member = make_member()
        term = give_term(member, "cinema-supporter")
        term.expires_on = timezone.localdate() + datetime.timedelta(days=5)
        term.save()
        html = self.page()
        self.assertIn("Expiring soon", html)
        self.assertIn(term.tier.name, html)
        self.assertIn(self.fmt(term.expires_on), html)

    def test_lapsed_shows_last_tier_and_expired_date(self) -> None:
        member = make_member()
        term = give_expired_term(member, "family-plus")
        html = self.page()
        self.assertIn("Lapsed", html)
        self.assertIn(term.tier.name, html)
        self.assertRegex(
            html, rf">Expired</p>\s*<p[^>]*>{self.fmt(term.expires_on)}</p>"
        )
        self.assertNotIn("None", html)
        self.assertNotIn("Free admissions this month", html)

    def test_upcoming_shows_tier_and_start_date(self) -> None:
        member = make_member()
        today = timezone.localdate()
        term = MembershipTerm.objects.create(
            member=member,
            tier=MembershipTier.objects.get(slug="cinema-supporter"),
            started_on=today + datetime.timedelta(days=10),
            expires_on=today + datetime.timedelta(days=375),
            price_paid=Decimal("120.00"),
        )
        html = self.page()
        self.assertIn("Not started yet", html)
        self.assertIn(term.tier.name, html)
        self.assertRegex(
            html, rf">Starts</p>\s*<p[^>]*>{self.fmt(term.started_on)}</p>"
        )
        self.assertNotIn("None", html)

    def test_member_with_no_terms_has_no_tier_line(self) -> None:
        make_member()
        html = self.page()
        self.assertNotIn(">Tier<", html)
        self.assertNotIn("None", html)


class MembershipLinkRequestTests(TestCase):
    """A member whose roster row carries another email can ask staff to link
    it, from the member home, with just their name."""

    ASK = (
        "If you're a member and your membership isn't showing up, don't panic. "
        "Ask us to link it to your dashboard account."
    )
    THANKS = "We got your request."

    def sign_in(self, email="nobody@example.com"):
        user = make_user(email, "pw12345", is_staff=False)
        self.client.force_login(user)
        return user

    def ask(self, first="Marguerite", last="Ouellette"):
        return self.client.post(
            reverse("dashboard:home"), {"first_name": first, "last_name": last}
        )

    def test_form_shown_only_without_a_roster_match(self) -> None:
        self.sign_in()
        html = self.client.get(reverse("dashboard:home")).content.decode()
        self.assertIn(self.ASK, html)
        self.assertIn('name="first_name"', html)
        self.assertIn('name="last_name"', html)
        make_member(email="nobody@example.com")
        html = self.client.get(reverse("dashboard:home")).content.decode()
        self.assertNotIn(self.ASK, html)
        self.assertNotIn('name="first_name"', html)

    def test_asking_saves_the_request_and_thanks(self) -> None:
        from audience.models import LinkRequestStatus, MembershipLinkRequest

        user = self.sign_in()
        resp = self.ask()
        self.assertRedirects(resp, reverse("dashboard:home"))
        request = MembershipLinkRequest.objects.get()
        self.assertEqual(
            (request.user, request.first_name, request.last_name, request.status),
            (user, "Marguerite", "Ouellette", LinkRequestStatus.NEW),
        )
        html = self.client.get(reverse("dashboard:home")).content.decode()
        self.assertIn(self.THANKS, html)
        self.assertNotIn('name="first_name"', html)

    def test_one_open_request_per_account(self) -> None:
        from audience.models import MembershipLinkRequest

        self.sign_in()
        self.ask()
        self.ask(first="Again")
        self.assertEqual(MembershipLinkRequest.objects.count(), 1)

    def test_blank_name_is_refused(self) -> None:
        from audience.models import MembershipLinkRequest

        self.sign_in()
        resp = self.ask(first="", last="")
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "This field is required.")
        self.assertEqual(MembershipLinkRequest.objects.count(), 0)

    def test_a_match_closes_the_open_request(self) -> None:
        from audience.models import LinkRequestStatus, MembershipLinkRequest

        self.sign_in()
        self.ask()
        make_member(email="nobody@example.com")
        html = self.client.get(reverse("dashboard:home")).content.decode()
        self.assertNotIn(self.THANKS, html)
        request = MembershipLinkRequest.objects.get()
        self.assertEqual(request.status, LinkRequestStatus.DONE)
        self.assertIsNotNone(request.resolved_at)

    def test_a_member_with_a_match_cannot_post_a_request(self) -> None:
        from audience.models import MembershipLinkRequest

        self.sign_in()
        make_member(email="nobody@example.com")
        self.assertRedirects(self.ask(), reverse("dashboard:home"))
        self.assertEqual(MembershipLinkRequest.objects.count(), 0)

    def test_staff_home_ignores_the_form(self) -> None:
        from audience.models import MembershipLinkRequest

        make_staff(email="staffer@example.com", password="pw12345")
        self.client.login(username="staffer@example.com", password="pw12345")
        resp = self.ask()
        self.assertNotEqual(resp.status_code, 500)
        self.assertEqual(MembershipLinkRequest.objects.count(), 0)


class RenewButtonTests(TestCase):
    """A member renews from their home; the join page prefills from here."""

    def setUp(self) -> None:
        patcher = mock.patch("dashboard.member_home.square_enabled", return_value=True)
        patcher.start()
        self.addCleanup(patcher.stop)
        for slug in ("cinema-supporter", "family-plus"):
            MembershipTier.objects.filter(slug=slug).update(
                square_variation_id=f"VAR-{slug}")
        self.member = make_member(email="m.o@example.com")
        self.client.force_login(make_user("m.o@example.com", "pw12345", is_staff=False))

    def html(self) -> str:
        return self.client.get(reverse("dashboard:home")).content.decode()

    def test_active_member_gets_renew_for_their_tier(self) -> None:
        give_term(self.member, "cinema-supporter")
        html = self.html()
        self.assertIn('href="/membership/join/cinema-supporter/"', html)
        self.assertIn(">Renew<", html)
        self.assertIn("or choose a different tier", html)
        self.assertIn('href="/membership/#tiers"', html)

    def test_lapsed_member_gets_renew_for_their_last_tier(self) -> None:
        give_expired_term(self.member, "family-plus")
        html = self.html()
        self.assertIn('href="/membership/join/family-plus/"', html)
        self.assertIn(">Renew<", html)

    def test_upcoming_member_gets_no_renew(self) -> None:
        today = timezone.localdate()
        MembershipTerm.objects.create(
            member=self.member,
            tier=MembershipTier.objects.get(slug="cinema-supporter"),
            started_on=today + datetime.timedelta(days=10),
            expires_on=today + datetime.timedelta(days=375),
            price_paid=Decimal("120.00"),
        )
        html = self.html()
        self.assertNotIn(">Renew<", html)
        self.assertNotIn("Choose a tier", html)

    def test_tier_not_sold_online_offers_the_tier_list_only(self) -> None:
        give_term(self.member, "cinema-supporter")
        MembershipTier.objects.filter(slug="cinema-supporter").update(
            square_variation_id="")
        html = self.html()
        self.assertNotIn(">Renew<", html)
        self.assertNotIn("/membership/join/", html)
        self.assertIn("Choose a tier to renew", html)
        self.assertIn('href="/membership/#tiers"', html)

    def test_square_off_offers_the_tier_list_only(self) -> None:
        give_term(self.member, "cinema-supporter")
        with mock.patch("dashboard.member_home.square_enabled", return_value=False):
            html = self.html()
        self.assertNotIn(">Renew<", html)
        self.assertIn("Choose a tier to renew", html)
