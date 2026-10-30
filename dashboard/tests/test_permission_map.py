"""Every dashboard view must 403 without its model permission."""

import re
import uuid
from pathlib import Path

from django.conf import settings
from django.test import TestCase
from django.urls import reverse

import dashboard.urls
from dashboard.tests.helpers import (
    DASHBOARD_PERMISSIONS,
    SPEC_PERMISSIONS,
    _declared_by_views,
    make_staff,
    permissions_except,
)
from dashboard.views import HomeView

UUID_NONE = uuid.UUID(int=0)

# (url_name, kwargs, method, permission). `permission` is one codename, or a
# tuple of alternatives for an any-of view. Kwargs use non-existent pks: the
# check runs in dispatch before any lookup, so 403 proves denial and 404
# proves the gate opened.
PERMISSION_TABLE: list[tuple[str, dict, str, str | tuple[str, ...]]] = [
    ("screens", {}, "get", "cinema.view_screen"),
    ("screen_create", {}, "get", "cinema.add_screen"),
    ("screen_edit", {"pk": 999999}, "get", "cinema.change_screen"),
    ("screen_delete", {"pk": 999999}, "post", "cinema.delete_screen"),
    ("film_search", {}, "get", "cinema.view_film"),
    ("film_search_tmdb", {}, "get", "cinema.add_film"),
    ("film_from_tmdb", {}, "post", "cinema.add_film"),
    ("engagements", {}, "get", "cinema.view_engagement"),
    ("engagement_detail", {"pk": 999999}, "get", "cinema.view_engagement"),
    (
        "engagement_social_card",
        {"pk": 999999, "platform": "facebook"},
        "get",
        "cinema.view_engagement",
    ),
    ("engagement_create", {}, "get", "cinema.add_engagement"),
    ("engagement_edit", {"pk": 999999}, "get", "cinema.change_engagement"),
    ("engagement_status", {"pk": 999999}, "post", "cinema.change_engagement"),
    ("engagement_square_retry", {"pk": 999999}, "post", "cinema.change_engagement"),
    ("engagement_delete", {"pk": 999999}, "post", "cinema.delete_engagement"),
    ("showtime_create", {"eng_pk": 999999}, "get", "cinema.add_showtime"),
    ("showtime_bulk", {"eng_pk": 999999}, "get", "cinema.add_showtime"),
    ("showtime_edit", {"pk": 999999}, "get", "cinema.change_showtime"),
    ("showtime_delete", {"pk": 999999}, "post", "cinema.delete_showtime"),
    ("showtime_orders", {"pk": 999999}, "get", "tickets.view_ticketorder"),
    ("showtime_orders_export", {"pk": 999999}, "get", "tickets.view_ticketorder"),
    ("tickets", {}, "get", "tickets.view_ticketorder"),
    ("ticket_orders", {}, "get", "tickets.view_ticketorder"),
    ("ticket_orders_export", {}, "get", "tickets.view_ticketorder"),
    ("showtime_allowance", {"pk": 999999}, "post", "cinema.change_showtime"),
    ("showtime_refund_all", {"pk": 999999}, "post", "tickets.refund_ticketorder"),
    ("ticket_order_arrive", {"pk": 999999}, "post", "tickets.change_ticketorder"),
    ("ticket_order_unarrive", {"pk": 999999}, "post", "tickets.change_ticketorder"),
    ("ticket_order_retry", {"pk": 999999}, "post", "tickets.change_ticketorder"),
    ("ticket_order_refund", {"pk": 999999}, "post", "tickets.refund_ticketorder"),
    ("polls", {}, "get", "cinema.view_poll"),
    ("poll_detail", {"pk": 999999}, "get", "cinema.view_poll"),
    ("poll_votes_export", {"pk": 999999}, "get", "cinema.view_poll"),
    ("poll_create", {}, "get", "cinema.add_poll"),
    ("poll_edit", {"pk": 999999}, "get", "cinema.change_poll"),
    ("poll_status", {"pk": 999999}, "post", "cinema.change_poll"),
    ("poll_announce", {"pk": 999999}, "get", "cinema.change_poll"),
    ("poll_delete", {"pk": 999999}, "post", "cinema.delete_poll"),
    ("poll_option_add", {"pk": 999999}, "post", "cinema.add_polloption"),
    (
        "poll_option_move",
        {"pk": 999999, "option_pk": 999999},
        "post",
        "cinema.change_polloption",
    ),
    (
        "poll_option_remove",
        {"pk": 999999, "option_pk": 999999},
        "post",
        "cinema.delete_polloption",
    ),
    (
        "poll_vote_remove",
        {"pk": 999999, "vote_pk": 999999},
        "post",
        "cinema.delete_vote",
    ),
    ("rental_inquiries", {}, "get", "cinema.view_rentalinquiry"),
    ("rental_inquiry_status", {"pk": 999999}, "post", "cinema.change_rentalinquiry"),
    ("ad_inquiries", {}, "get", "cinema.view_adinquiry"),
    ("ad_inquiry_status", {"pk": 999999}, "post", "cinema.change_adinquiry"),
    ("voicemails", {}, "get", "phone.view_voicemail"),
    ("voicemail_audio", {"pk": 999999}, "get", "phone.view_voicemail"),
    ("voicemail_status", {"pk": 999999}, "post", "phone.change_voicemail"),
    ("voicemail_notes", {"pk": 999999}, "post", "phone.change_voicemail"),
    ("voicemail_delete", {"pk": 999999}, "post", "phone.delete_voicemail"),
    ("members", {}, "get", "audience.view_member"),
    ("member_detail", {"pk": 999999}, "get", "audience.view_member"),
    ("members_export", {}, "get", "audience.view_member"),
    ("member_create", {}, "get", "audience.add_member"),
    ("member_edit", {"pk": 999999}, "get", "audience.change_member"),
    ("member_delete", {"pk": 999999}, "post", "audience.delete_member"),
    ("membership_link_requests", {}, "get", "audience.view_membershiplinkrequest"),
    (
        "membership_link_request_status",
        {"pk": 999999},
        "post",
        "audience.change_membershiplinkrequest",
    ),
    ("terms", {}, "get", "audience.view_membershipterm"),
    ("terms_export", {}, "get", "audience.view_membershipterm"),
    ("term_create", {"pk": 999999}, "get", "audience.add_membershipterm"),
    ("term_edit", {"pk": 999999}, "get", "audience.change_membershipterm"),
    ("term_delete", {"pk": 999999}, "post", "audience.delete_membershipterm"),
    ("free_admission_redeem", {"pk": 999999}, "post", "audience.add_freeadmission"),
    ("free_admission_delete", {"pk": 999999}, "post", "audience.delete_freeadmission"),
    ("tiers", {}, "get", "audience.view_membershiptier"),
    ("tier_create", {}, "get", "audience.add_membershiptier"),
    ("tier_edit", {"pk": 999999}, "get", "audience.change_membershiptier"),
    ("tier_listing", {"pk": 999999}, "post", "audience.change_membershiptier"),
    ("tier_delete", {"pk": 999999}, "post", "audience.delete_membershiptier"),
    ("benefit_create", {}, "get", "audience.add_membershipbenefit"),
    ("benefit_edit", {"pk": 999999}, "get", "audience.change_membershipbenefit"),
    ("benefit_delete", {"pk": 999999}, "post", "audience.delete_membershipbenefit"),
    ("square_sales", {}, "get", "boxoffice.view_membershipsale"),
    ("square_sale_retry", {"pk": 999999}, "post", "boxoffice.change_membershipsale"),
    ("subscribers", {}, "get", "audience.view_subscriber"),
    ("subscribers_export", {}, "get", "audience.view_subscriber"),
    ("newsletter_issues", {}, "get", "newsletter.view_issue"),
    ("newsletter_issue_preview", {"pk": 999999}, "get", "newsletter.view_issue"),
    ("blog", {}, "get", "blog.view_blogpost"),
    ("blog_post_preview", {"pk": UUID_NONE}, "get", "blog.view_blogpost"),
    ("blog_post_create", {}, "get", "blog.add_blogpost"),
    ("blog_post_edit", {"pk": UUID_NONE}, "get", "blog.change_blogpost"),
    (
        "blog_markdown_preview",
        {},
        "post",
        ("blog.add_blogpost", "blog.change_blogpost"),
    ),
    ("blog_post_delete", {"pk": UUID_NONE}, "post", "blog.delete_blogpost"),
    ("blog_author_create", {}, "get", "blog.add_blogauthor"),
    ("blog_author_edit", {"pk": UUID_NONE}, "get", "blog.change_blogauthor"),
    ("blog_author_delete", {"pk": UUID_NONE}, "post", "blog.delete_blogauthor"),
    ("blog_category_create", {}, "get", "blog.add_blogcategory"),
    ("blog_category_edit", {"pk": UUID_NONE}, "get", "blog.change_blogcategory"),
    ("blog_category_delete", {"pk": UUID_NONE}, "post", "blog.delete_blogcategory"),
]


class PermissionMapTests(TestCase):
    def test_every_view_enforces_its_permission(self) -> None:
        for i, (url_name, kwargs, method, permission) in enumerate(
            PERMISSION_TABLE
        ):
            with self.subTest(url_name=url_name):
                url = reverse(f"dashboard:{url_name}", kwargs=kwargs)
                alternatives = (
                    (permission,) if isinstance(permission, str) else permission
                )

                make_staff(
                    email=f"deny-{i}@example.com",
                    perms=permissions_except(*alternatives),
                )
                self.client.login(username=f"deny-{i}@example.com", password="pw12345")
                response = getattr(self.client, method)(url)
                self.assertEqual(response.status_code, 403)
                self.client.logout()

                make_staff(email=f"allow-{i}@example.com", perms=(alternatives[0],))
                self.client.login(username=f"allow-{i}@example.com", password="pw12345")
                response = getattr(self.client, method)(url)
                self.assertNotEqual(response.status_code, 403)
                self.client.logout()

    def test_every_view_but_home_declares_a_permission(self) -> None:
        for pattern in dashboard.urls.urlpatterns:
            view_class = pattern.callback.view_class
            with self.subTest(view=view_class.__name__):
                if view_class is HomeView:
                    self.assertEqual(view_class.permission_required, ())
                else:
                    self.assertTrue(view_class.permission_required)

    def test_every_url_is_in_the_table(self) -> None:
        names = {p.name for p in dashboard.urls.urlpatterns} - {"home"}
        self.assertEqual(names, {row[0] for row in PERMISSION_TABLE})

    def test_declared_permissions_match_the_spec(self) -> None:
        declared = _declared_by_views()
        self.assertEqual(declared - SPEC_PERMISSIONS, set())
        # Only templates and the home page use these four; no view declares them.
        self.assertEqual(
            SPEC_PERMISSIONS - declared,
            {
                "blog.view_blogauthor",
                "blog.view_blogcategory",
                "boxoffice.view_salespull",
                "cinema.view_showtime",
            },
        )


class TemplatePermissionStringTests(TestCase):
    def test_template_permission_strings_exist(self) -> None:
        base = Path(settings.BASE_DIR)
        found = set()
        for rel in ("dashboard/templates/dashboard", "blog/templates/blog"):
            for path in (base / rel).rglob("*.html"):
                text = path.read_text(encoding="utf-8")
                found.update(
                    f"{app}.{code}"
                    for app, code in re.findall(r"perms\.(\w+)\.(\w+)", text)
                )
        self.assertTrue(found)
        self.assertEqual(sorted(found - set(DASHBOARD_PERMISSIONS)), [])
