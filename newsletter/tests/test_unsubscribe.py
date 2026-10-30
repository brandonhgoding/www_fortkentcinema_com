"""The public unsubscribe page: one GET to ask, one POST to leave, and a
done page whatever the token, so the link never says who is on the list."""

import uuid

from django.test import Client, TestCase, override_settings
from django.urls import reverse

from audience.models import Subscriber, SubscriberStatus, SubscriptionChange
from newsletter.links import mask_email, unsubscribe_url


class UnsubscribeViewTests(TestCase):
    def setUp(self):
        self.sub, _ = Subscriber.objects.record("brandon@example.com", source="site")
        self.url = reverse("list_unsubscribe", args=[self.sub.unsubscribe_token])

    def test_get_known_token_asks(self):
        response = self.client.get(self.url)
        html = response.content.decode()
        self.assertEqual(response.status_code, 200)
        self.assertIn("b•••@example.com", html)
        self.assertIn('<form method="post"', html)
        self.assertIn(">Unsubscribe</button>", html)
        self.assertIn('name="robots" content="noindex, nofollow"', html)
        self.assertEqual(response["X-Robots-Tag"], "noindex, nofollow")
        self.sub.refresh_from_db()
        self.assertEqual(self.sub.status, SubscriberStatus.ACTIVE)

    def test_post_unsubscribes(self):
        response = self.client.post(self.url)
        self.assertEqual(response.status_code, 200)
        self.assertIn("You're off the list.", response.content.decode())
        self.sub.refresh_from_db()
        self.assertEqual(self.sub.status, SubscriberStatus.UNSUBSCRIBED)
        self.assertIsNotNone(self.sub.unsubscribed_at)
        self.assertEqual(
            SubscriptionChange.objects.filter(
                subscriber=self.sub, status=SubscriberStatus.UNSUBSCRIBED
            ).count(),
            1,
        )

    def test_unknown_token_get_and_post_show_done(self):
        url = reverse("list_unsubscribe", args=[uuid.uuid4()])
        for method in (self.client.get, self.client.post):
            response = method(url)
            self.assertEqual(response.status_code, 200)
            self.assertIn("You're off the list.", response.content.decode())

    def test_one_click_post_without_csrf(self):
        client = Client(enforce_csrf_checks=True)
        response = client.post(self.url, {"List-Unsubscribe": "One-Click"})
        self.assertEqual(response.status_code, 200)
        self.sub.refresh_from_db()
        self.assertEqual(self.sub.status, SubscriberStatus.UNSUBSCRIBED)

    def test_already_unsubscribed_post_is_noop(self):
        self.client.post(self.url)
        self.sub.refresh_from_db()
        first = self.sub.unsubscribed_at
        response = self.client.post(self.url)
        self.assertEqual(response.status_code, 200)
        self.sub.refresh_from_db()
        self.assertEqual(self.sub.unsubscribed_at, first)
        self.assertEqual(
            SubscriptionChange.objects.filter(
                subscriber=self.sub, status=SubscriberStatus.UNSUBSCRIBED
            ).count(),
            1,
        )

    def test_done_page_links_to_rejoin(self):
        html = self.client.post(self.url).content.decode()
        self.assertIn('href="/#coming-soon"', html)
        self.assertIn("Changed your mind? Rejoin", html)

    def test_not_in_sitemap(self):
        xml = self.client.get("/sitemap.xml").content.decode()
        self.assertNotIn("/unsubscribe/", xml)


class LinkTests(TestCase):
    def test_mask_email(self):
        self.assertEqual(mask_email("brandon@example.com"), "b•••@example.com")
        self.assertEqual(mask_email("a@b.co"), "a•••@b.co")

    @override_settings(TICKETS_BASE_URL="https://www.fortkentcinema.com")
    def test_unsubscribe_url_is_absolute(self):
        sub, _ = Subscriber.objects.record("x@example.com", source="site")
        self.assertEqual(
            unsubscribe_url(sub),
            f"https://www.fortkentcinema.com/unsubscribe/{sub.unsubscribe_token}",
        )
