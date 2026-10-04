from django.test import TestCase
from django.utils import timezone

from audience.models import MembershipBenefit, MembershipTier
from blog.models import BlogAuthor, BlogCategory, BlogPost


class SitemapTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        a = BlogAuthor.objects.create(first_name="A", last_name="B")
        c = BlogCategory.objects.create(name="News")
        cls.post = BlogPost.objects.create(title="P1", subtitle="p-one", author=a,
                                           category=c, post_date="2026-01-01", content="x")

    def test_sitemap_lists_static_and_posts(self):
        resp = self.client.get("/sitemap.xml")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp["Content-Type"].split(";")[0], "application/xml")
        body = resp.content.decode()
        self.assertIn("/membership/", body)
        self.assertIn("/blog/", body)
        self.assertIn(f"/blog/{self.post.slug}", body)

    def test_robots_txt(self):
        resp = self.client.get("/robots.txt")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp["Content-Type"].split(";")[0], "text/plain")
        self.assertIn("Sitemap:", resp.content.decode())

    def test_blogpost_get_absolute_url(self):
        self.assertEqual(self.post.get_absolute_url(), f"/blog/{self.post.slug}")


class MembershipLastmodTests(TestCase):
    """/membership/ is rendered from the tier catalogue, so editing a tier
    or a listed perk moves the page with nobody touching the template."""

    def lastmod(self):
        from web.sitemaps import StaticViewSitemap

        return StaticViewSitemap().lastmod("membership")

    def setUp(self):
        from web.sitemaps import STATIC_PAGE_LASTMOD

        self.edited = STATIC_PAGE_LASTMOD["membership"]
        self.today = timezone.localdate()
        self.assertGreater(self.today, self.edited)

    def test_an_untouched_catalogue_falls_back_to_the_template_date(self):
        self.assertEqual(self.lastmod(), self.edited)

    def test_a_tier_edit_moves_it(self):
        tier = MembershipTier.objects.get(slug="individual")
        tier.price = 65
        tier.save()
        self.assertEqual(self.lastmod(), self.today)

    def test_a_listed_perk_edit_moves_it(self):
        perk = MembershipBenefit.objects.get(name="10% off rentals")
        perk.name = "10% off rentals & parties"
        perk.save()
        self.assertEqual(self.lastmod(), self.today)

    def test_a_perk_no_listed_tier_carries_does_not(self):
        MembershipBenefit.objects.create(name="Not on any tier")
        self.assertEqual(self.lastmod(), self.edited)
