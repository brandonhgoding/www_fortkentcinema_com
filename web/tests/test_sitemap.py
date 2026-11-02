from django.test import TestCase


class SitemapTests(TestCase):
    def test_sitemap_lists_the_static_pages(self):
        resp = self.client.get("/sitemap.xml")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp["Content-Type"].split(";")[0], "application/xml")
        body = resp.content.decode()
        self.assertIn("/rentals/", body)

    def test_robots_txt(self):
        resp = self.client.get("/robots.txt")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp["Content-Type"].split(";")[0], "text/plain")
        self.assertIn("Sitemap:", resp.content.decode())
