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
        self.assertIn(
            f"1 / {member.free_admission_allowance}", html
        )

    def test_member_without_match_sees_join_prompt(self) -> None:
        self.sign_in("nobody@example.com")
        resp = self.client.get(reverse("dashboard:home"))
        html = resp.content.decode()
        self.assertIsNone(resp.context["member"])
        self.assertIn(
            "No membership on file for this email. Join at the box office "
            "before any show.",
            html,
        )
        self.assertIn('href="/membership/"', html)

    def test_member_sidebar_has_no_staff_links(self) -> None:
        self.sign_in()
        html = self.client.get(reverse("dashboard:home")).content.decode()
        nav = re.search(
            r'data-cy="sidebar-nav".*?</nav>', html, re.S
        ).group(0)
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
        self.assertEqual(
            self.client.get(url, HTTP_HX_REQUEST="true").status_code, 403
        )

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
        self.assertIn(f"Expired {self.fmt(term.expires_on)}", html)
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
        self.assertIn(f"Starts {self.fmt(term.started_on)}", html)
        self.assertNotIn("None", html)

    def test_member_with_no_terms_has_no_tier_line(self) -> None:
        make_member()
        html = self.page()
        self.assertNotIn(">Tier<", html)
        self.assertNotIn("None", html)
