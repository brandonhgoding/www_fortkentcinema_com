import datetime
import json
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from audience.models import Member, MembershipTerm

User = get_user_model()


def make_member(first="Ada", last="Lovelace", email="ada@example.com", **kwargs):
    return Member.objects.create(
        first_name=first, last_name=last, email=email, **kwargs
    )


def give_term(member, days_left=100, tier="individual"):
    today = timezone.localdate()
    return MembershipTerm.objects.create(
        member=member,
        tier=tier,
        started_on=today - datetime.timedelta(days=30),
        expires_on=today + datetime.timedelta(days=days_left),
        price_paid=Decimal("60.00"),
    )


class MemberListTests(TestCase):
    def setUp(self) -> None:
        User.objects.create_user(username="s", password="pw12345", is_staff=True)
        self.client.login(username="s", password="pw12345")

    def test_empty_state(self) -> None:
        html = self.client.get(reverse("dashboard:members")).content.decode()
        self.assertIn("empty-state", html)
        self.assertIn("No Members Yet", html)

    def test_rows_show_name_email_tier_and_expiry(self) -> None:
        member = make_member()
        give_term(member)
        html = self.client.get(reverse("dashboard:members")).content.decode()
        self.assertIn("Lovelace", html)
        self.assertIn("ada@example.com", html)
        self.assertIn("Individual", html)  # tier label, not the slug

    def test_status_pills(self) -> None:
        give_term(make_member(email="a@example.com"), days_left=200)
        give_term(make_member("Soon", "Expiring", "b@example.com"), days_left=5)
        make_member("No", "Terms", "c@example.com")
        html = self.client.get(reverse("dashboard:members")).content.decode()
        self.assertIn("Active", html)
        self.assertIn("Expiring soon", html)
        self.assertIn("Lapsed", html)

    def test_query_filter_matches_name_and_email(self) -> None:
        give_term(make_member("Ada", "Lovelace", "ada@example.com"))
        give_term(make_member("Grace", "Hopper", "grace@example.com"))

        by_name = self.client.get(
            reverse("dashboard:members"), {"q": "hopper"}
        ).content.decode()
        self.assertIn("Hopper", by_name)
        self.assertNotIn("Lovelace", by_name)

        by_email = self.client.get(
            reverse("dashboard:members"), {"q": "ada@"}
        ).content.decode()
        self.assertIn("Lovelace", by_email)
        self.assertNotIn("Hopper", by_email)

    def test_status_filter(self) -> None:
        give_term(make_member("Cur", "Rent", "current@example.com"))
        make_member("No", "Terms", "never@example.com")

        active = self.client.get(
            reverse("dashboard:members"), {"status": "active"}
        ).content.decode()
        self.assertIn("Rent", active)
        self.assertNotIn("Terms", active)

        lapsed = self.client.get(
            reverse("dashboard:members"), {"status": "lapsed"}
        ).content.decode()
        self.assertIn("Terms", lapsed)
        self.assertNotIn("Rent", lapsed)

    def test_unknown_status_filter_is_ignored(self) -> None:
        give_term(make_member())
        html = self.client.get(
            reverse("dashboard:members"), {"status": "nonsense"}
        ).content.decode()
        self.assertIn("Lovelace", html)

    def test_requires_staff(self) -> None:
        self.client.logout()
        self.assertEqual(
            self.client.get(reverse("dashboard:members")).status_code, 302
        )
        User.objects.create_user(username="p", password="pw12345", is_staff=False)
        self.client.login(username="p", password="pw12345")
        self.assertEqual(
            self.client.get(reverse("dashboard:members")).status_code, 403
        )

    def test_members_css_linked(self) -> None:
        html = self.client.get(reverse("dashboard:members")).content.decode()
        self.assertIn("dashboard/css/members.css", html)

    def test_sidebar_links_to_members(self) -> None:
        html = self.client.get(reverse("dashboard:home")).content.decode()
        self.assertIn(reverse("dashboard:members"), html)


class MemberCreateEditTests(TestCase):
    def setUp(self) -> None:
        User.objects.create_user(username="s", password="pw12345", is_staff=True)
        self.client.login(username="s", password="pw12345")

    def test_get_create_form(self) -> None:
        html = self.client.get(reverse("dashboard:member_create")).content.decode()
        self.assertIn('id="member-form"', html)
        self.assertIn("Add Member", html)

    def test_post_create_valid(self) -> None:
        resp = self.client.post(
            reverse("dashboard:member_create"),
            {
                "first_name": "Ada",
                "last_name": "Lovelace",
                "email": "Ada@Example.com",
                "phone": "",
                "notes": "",
            },
        )
        self.assertEqual(resp.status_code, 200)
        member = Member.objects.get()
        self.assertEqual(member.email, "ada@example.com")

        triggers = json.loads(resp["HX-Trigger"])
        self.assertTrue(triggers["close-drawer"])
        self.assertEqual(triggers["dashboard-toast"]["kind"], "success")
        self.assertIn('hx-swap-oob="true"', resp.content.decode())

    def test_post_create_invalid_redisplays_the_form(self) -> None:
        resp = self.client.post(
            reverse("dashboard:member_create"),
            {"first_name": "Ada", "last_name": "Lovelace", "email": "not-an-email"},
        )
        self.assertEqual(resp.status_code, 200)
        self.assertIn('id="member-form"', resp.content.decode())
        self.assertEqual(Member.objects.count(), 0)

    def test_post_edit_updates(self) -> None:
        member = make_member()
        self.client.post(
            reverse("dashboard:member_edit", args=[member.pk]),
            {
                "first_name": "Ada",
                "last_name": "King",
                "email": "ada@example.com",
                "phone": "207-555-0100",
                "notes": "",
            },
        )
        member.refresh_from_db()
        self.assertEqual(member.last_name, "King")
        self.assertEqual(member.phone, "207-555-0100")

    def test_requires_staff(self) -> None:
        self.client.logout()
        self.assertEqual(
            self.client.get(reverse("dashboard:member_create")).status_code, 302
        )


class MemberDeleteTests(TestCase):
    def setUp(self) -> None:
        User.objects.create_user(username="s", password="pw12345", is_staff=True)
        self.client.login(username="s", password="pw12345")

    def test_delete_removes_the_member_and_their_terms(self) -> None:
        member = make_member()
        give_term(member)
        resp = self.client.post(reverse("dashboard:member_delete", args=[member.pk]))
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(Member.objects.count(), 0)
        self.assertEqual(MembershipTerm.objects.count(), 0)

    def test_delete_toasts(self) -> None:
        member = make_member()
        resp = self.client.post(reverse("dashboard:member_delete", args=[member.pk]))
        triggers = json.loads(resp["HX-Trigger"])
        self.assertEqual(triggers["dashboard-toast"]["kind"], "success")

    def test_confirm_copy_names_the_term_count(self) -> None:
        member = make_member()
        give_term(member)
        html = self.client.get(reverse("dashboard:members")).content.decode()
        self.assertIn("1 membership term", html)
