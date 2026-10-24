import re

from accounts.tests.factories import make_user
from audience.models import FreeAdmission
from dashboard.tests.helpers import make_staff
from dashboard.tests.test_free_admissions import give_term, make_member
from django.test import TestCase
from django.urls import reverse


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
