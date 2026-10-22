"""Every dashboard view must 403 without its model permission."""

from django.test import TestCase
from django.urls import reverse

from dashboard.tests.helpers import make_staff, permissions_except

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
    ("showtime_refund_all", {"pk": 999999}, "post", "tickets.change_ticketorder"),
    ("ticket_order_arrive", {"pk": 999999}, "post", "tickets.change_ticketorder"),
    ("ticket_order_unarrive", {"pk": 999999}, "post", "tickets.change_ticketorder"),
    ("ticket_order_retry", {"pk": 999999}, "post", "tickets.change_ticketorder"),
    ("ticket_order_refund", {"pk": 999999}, "post", "tickets.change_ticketorder"),
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
    ("terms", {}, "get", "audience.view_membershipterm"),
    ("terms_export", {}, "get", "audience.view_membershipterm"),
    ("term_create", {"pk": 999999}, "get", "audience.add_membershipterm"),
    ("term_edit", {"pk": 999999}, "get", "audience.change_membershipterm"),
    ("term_delete", {"pk": 999999}, "post", "audience.delete_membershipterm"),
    ("free_admission_redeem", {"pk": 999999}, "post", "audience.add_freeadmission"),
    ("free_admission_delete", {"pk": 999999}, "post", "audience.delete_freeadmission"),
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
                    username=f"deny-{i}", perms=permissions_except(*alternatives)
                )
                self.client.login(username=f"deny-{i}", password="pw12345")
                response = getattr(self.client, method)(url)
                self.assertEqual(response.status_code, 403)
                self.client.logout()

                make_staff(username=f"allow-{i}", perms=(alternatives[0],))
                self.client.login(username=f"allow-{i}", password="pw12345")
                response = getattr(self.client, method)(url)
                self.assertNotEqual(response.status_code, 403)
                self.client.logout()
