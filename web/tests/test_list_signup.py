import re
from datetime import timedelta
from unittest import mock

from django.core import mail
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from audience.models import Subscriber, SubscriberStatus
from web.list_signup import load_confirm_token, source_for

DONE = "Almost there: check your inbox for a link to confirm."
ERROR = "That doesn&#x27;t look like an email address."


def post(client, htmx=True, **data):
    data = {"email": "fan@example.com", "location": "movie_page", "website": "", **data}
    extra = {"HTTP_HX_REQUEST": "true"} if htmx else {}
    return client.post(reverse("list_signup"), data, **extra)


class ListSignupTests(TestCase):
    def test_new_address_gets_one_email_with_a_working_link(self):
        r = post(self.client)
        self.assertContains(r, DONE)
        self.assertEqual(len(mail.outbox), 1)
        msg = mail.outbox[0]
        self.assertEqual(msg.subject, "Confirm your Fort Kent Cinema emails")
        self.assertEqual(msg.to, ["fan@example.com"])
        self.assertIn("every Thursday", msg.body)
        self.assertIn("Didn't ask for this?", msg.body)
        link = re.search(r"http://testserver(/subscribe/confirm/\S+)", msg.body).group(
            1
        )
        sub, issued = load_confirm_token(link.rsplit("/", 1)[1])
        self.assertEqual(sub.email, "fan@example.com")
        self.assertIsNotNone(issued.tzinfo)
        self.assertLess(abs(timezone.now() - issued), timedelta(minutes=1))
        self.assertIsNotNone(Subscriber.objects.get().confirmation_sent_at)

    def test_token_keeps_sub_second_issue_time(self):
        post(self.client)
        token = re.search(r"/subscribe/confirm/(\S+)", mail.outbox[0].body).group(1)
        _, issued = load_confirm_token(token)
        self.assertNotEqual(issued.microsecond, 0)

    def test_bad_token_and_deleted_row_load_as_none(self):
        self.assertIsNone(load_confirm_token("nonsense"))
        post(self.client)
        token = re.search(r"/subscribe/confirm/(\S+)", mail.outbox[0].body).group(1)
        Subscriber.objects.all().delete()
        self.assertIsNone(load_confirm_token(token))

    def test_expired_token_loads_as_none(self):
        post(self.client)
        token = re.search(r"/subscribe/confirm/(\S+)", mail.outbox[0].body).group(1)
        with mock.patch("django.core.signing.time.time", return_value=9e9):
            self.assertIsNone(load_confirm_token(token))

    def test_active_address_gets_the_same_reply_and_no_email(self):
        Subscriber.objects.record("fan@example.com", source="site")
        self.assertContains(post(self.client), DONE)
        self.assertEqual(mail.outbox, [])

    def test_second_submit_within_the_hour_sends_nothing(self):
        post(self.client)
        self.assertContains(post(self.client), DONE)
        self.assertEqual(len(mail.outbox), 1)

    def test_submit_after_the_hour_sends_again(self):
        post(self.client)
        Subscriber.objects.update(
            confirmation_sent_at=timezone.now() - timedelta(hours=2)
        )
        post(self.client)
        self.assertEqual(len(mail.outbox), 2)

    def test_honeypot_gets_the_same_reply_and_nothing_happens(self):
        r = post(self.client, website="http://spam")
        self.assertContains(r, DONE)
        self.assertFalse(Subscriber.objects.exists())
        self.assertEqual(mail.outbox, [])

    def test_bad_addresses_are_refused(self):
        for bad in (
            "",
            "a@b",
            "x" * 300 + "@example.com",
            "x@example.com\nBcc: y@example.com",
        ):
            r = post(self.client, email=bad)
            self.assertContains(r, ERROR)
        self.assertFalse(Subscriber.objects.exists())
        self.assertEqual(mail.outbox, [])

    def test_bad_address_keeps_what_was_typed(self):
        self.assertContains(post(self.client, email="a@b"), 'value="a@b"')

    def test_location_becomes_the_source(self):
        post(self.client, location="home_empty")
        self.assertEqual(Subscriber.objects.get().source, "home_empty")
        post(self.client, email="two@example.com", location="evil")
        self.assertEqual(Subscriber.objects.get(email="two@example.com").source, "site")

    def test_source_for(self):
        self.assertEqual(source_for("home_showtimes"), "home_showtimes")
        self.assertEqual(source_for("nope"), "site")

    def test_plain_post_renders_a_page(self):
        r = post(self.client, htmx=False)
        self.assertTemplateUsed(r, "web/list_signup.html")
        self.assertContains(r, DONE)
        self.assertContains(r, "noindex, nofollow")

    def test_plain_page_links_back_only_to_this_site(self):
        r = self.client.post(
            reverse("list_signup"),
            {"email": "fan@example.com", "location": "x"},
            HTTP_REFERER="http://testserver/movies/foo",
        )
        self.assertContains(r, 'href="http://testserver/movies/foo"')
        r = self.client.post(
            reverse("list_signup"),
            {"email": "fan@example.com", "location": "x"},
            HTTP_REFERER="http://evil.example/x",
        )
        self.assertNotContains(r, "evil.example")

    def test_smtp_failure_still_replies_and_can_retry(self):
        with mock.patch("web.list_signup.EmailMessage.send", side_effect=OSError):
            with self.assertLogs("web.list_signup", level="ERROR"):
                self.assertContains(post(self.client), DONE)
        self.assertIsNone(Subscriber.objects.get().confirmation_sent_at)
        post(self.client)
        self.assertEqual(len(mail.outbox), 1)

    def test_failed_send_restores_the_earlier_send_time(self):
        post(self.client)
        earlier = timezone.now() - timedelta(hours=3)
        Subscriber.objects.update(confirmation_sent_at=earlier)
        with mock.patch("web.list_signup.EmailMessage.send", side_effect=OSError):
            with self.assertLogs("web.list_signup", level="ERROR"):
                post(self.client)
        self.assertEqual(Subscriber.objects.get().confirmation_sent_at, earlier)

    def test_a_claim_already_taken_sends_nothing(self):
        # Another request claimed the send after request_signup returned.
        real = Subscriber.objects.request_signup

        def raced(*args, **kwargs):
            sub = real(*args, **kwargs)
            Subscriber.objects.filter(pk=sub.pk).update(
                confirmation_sent_at=timezone.now()
            )
            return sub

        with mock.patch.object(Subscriber.objects, "request_signup", raced):
            self.assertContains(post(self.client), DONE)
        self.assertEqual(mail.outbox, [])

    def test_pending_status_is_stored(self):
        post(self.client)
        self.assertEqual(Subscriber.objects.get().status, SubscriberStatus.PENDING)

    def test_get_is_not_allowed(self):
        self.assertEqual(self.client.get(reverse("list_signup")).status_code, 405)
