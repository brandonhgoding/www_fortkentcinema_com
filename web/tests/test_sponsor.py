import datetime

from cinema.models import Studio, StudioTitle
from django.test import TestCase
from django.urls import reverse


class SponsorPageTests(TestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        cls.studio = Studio.objects.create(
            name="Universal Pictures", slug="universal"
        )
        cls.wild = StudioTitle.objects.create(
            studio=cls.studio, original_title="WILD ROBOT, THE",
            title="The Wild Robot", release_date=datetime.date(2024, 9, 27),
            mpa_rating="PG", runtime_minutes=102, aspect_ratio="Scope",
        )
        cls.jaws = StudioTitle.objects.create(
            studio=cls.studio, original_title="JAWS", title="Jaws",
            release_date=datetime.date(1975, 6, 20),
            mpa_rating="PG", runtime_minutes=124,
        )
        cls.hidden = StudioTitle.objects.create(
            studio=cls.studio, original_title="HIDDEN ONE", title="Hidden One",
            release_date=datetime.date(2020, 1, 1), is_available=False,
        )

    def test_page_returns_200_and_uses_templates(self):
        response = self.client.get(reverse("sponsor"))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "base.html")
        self.assertTemplateUsed(response, "web/sponsor.html")

    def test_no_template_comment_leaks_into_page(self):
        html = self.client.get(reverse("sponsor")).content.decode()
        self.assertNotIn("{#", html)
        self.assertNotIn("{% comment %}", html)

    def test_lists_available_titles_only(self):
        # "The Wild Robot" cannot be checked via raw HTML: the page's static
        # worked example names it unconditionally (see
        # test_inactive_studio_titles_are_hidden below), so that assertion
        # would pass even if the table rendered empty. Checked via context
        # instead; "Jaws" and "Hidden One" have no such collision, so those
        # stay as real HTML assertions proving the table actually renders.
        response = self.client.get(reverse("sponsor"))
        titles = [t.title for t in response.context["titles"]]
        self.assertIn("The Wild Robot", titles)

        html = response.content.decode()
        self.assertIn("Jaws", html)
        self.assertNotIn("Hidden One", html)

    def test_inactive_studio_titles_are_hidden(self):
        # Checked against context, not raw HTML: the page's static worked
        # example also names "The Wild Robot" (a real, approved sponsorship),
        # so a whole-page substring scan would false-fail regardless of
        # whether the queryset actually excludes the inactive studio.
        self.studio.is_active = False
        self.studio.save()
        response = self.client.get(reverse("sponsor"))
        titles = [t.title for t in response.context["titles"]]
        self.assertNotIn("The Wild Robot", titles)

    def test_search_filters_by_title(self):
        response = self.client.get(reverse("sponsor"), {"q": "wild"})
        titles = [t.title for t in response.context["titles"]]
        self.assertEqual(titles, ["The Wild Robot"])

    def test_search_is_case_insensitive(self):
        response = self.client.get(reverse("sponsor"), {"q": "JAWS"})
        self.assertEqual([t.title for t in response.context["titles"]], ["Jaws"])

    def test_decade_filter(self):
        response = self.client.get(reverse("sponsor"), {"decade": "1970"})
        self.assertEqual([t.title for t in response.context["titles"]], ["Jaws"])

    def test_decade_never_500s_across_a_swept_input_space(self):
        # Regression sweep. str.isdigit() is True for Unicode digits that
        # int() can't always turn into a safe year ('²', '१९७०'), and even a
        # plain ASCII digit string can be zero, negative-looking, absurdly
        # long, or simply out of any calendar's range — all of which must
        # be *ignored*, not 500. Every one of these must return 200.
        inputs = [
            "²", "0", "1", "999", "1800", "1970", "2100", "2101", "9999",
            "10000", "12000", "99999", "9999999999999",
            "000000000000000000001", "-5", "abc", "", "1970.5",
            "१९७०",  # Devanagari digits: isdigit() True, isascii() False
            "9" * 500,
        ]
        for decade in inputs:
            with self.subTest(decade=decade):
                response = self.client.get(reverse("sponsor"), {"decade": decade})
                self.assertEqual(response.status_code, 200)

    def test_decade_upper_bound_is_inclusive_and_still_filters(self):
        # The accepted bound must do more than "not crash" — it must still
        # filter, so a title sitting right on the upper edge is included.
        future = StudioTitle.objects.create(
            studio=self.studio, original_title="FUTURE FILM",
            title="Future Film", release_date=datetime.date(2105, 1, 1),
        )
        response = self.client.get(reverse("sponsor"), {"decade": "2100"})
        self.assertEqual(response.status_code, 200)
        titles = [t.title for t in response.context["titles"]]
        self.assertEqual(titles, [future.title])

    def test_decade_one_past_the_upper_bound_is_ignored_not_filtered(self):
        future = StudioTitle.objects.create(
            studio=self.studio, original_title="FUTURE FILM",
            title="Future Film", release_date=datetime.date(2105, 1, 1),
        )
        response = self.client.get(reverse("sponsor"), {"decade": "2101"})
        self.assertEqual(response.status_code, 200)
        titles = [t.title for t in response.context["titles"]]
        # Out of range means the param is dropped entirely, not applied —
        # every available title shows, including the one from 2105.
        self.assertIn(future.title, titles)
        self.assertIn("Jaws", titles)

    def test_rating_filter(self):
        response = self.client.get(reverse("sponsor"), {"rating": "PG"})
        self.assertEqual(len(response.context["titles"]), 2)

    def test_sort_by_year_descending(self):
        response = self.client.get(reverse("sponsor"), {"sort": "-year"})
        titles = [t.title for t in response.context["titles"]]
        self.assertEqual(titles, ["The Wild Robot", "Jaws"])

    def test_unknown_sort_falls_back_to_title(self):
        # Never interpolate raw querystring into order_by.
        response = self.client.get(reverse("sponsor"), {"sort": "runtime; DROP TABLE"})
        self.assertEqual(response.status_code, 200)
        titles = [t.title for t in response.context["titles"]]
        self.assertEqual(titles, ["Jaws", "The Wild Robot"])

    def test_pagination_is_fifty_per_page(self):
        response = self.client.get(reverse("sponsor"))
        self.assertEqual(response.context["paginator"].per_page, 50)

    def test_tiers_are_in_context_with_the_agreed_prices(self):
        tiers = self.client.get(reverse("sponsor")).context["tiers"]
        self.assertEqual([t["price"] for t in tiers], [299, 499, 799])

    def test_page_names_the_real_sponsor_example(self):
        html = self.client.get(reverse("sponsor")).content.decode()
        self.assertIn("A.H. Custom Carpentry", html)
        self.assertIn("The Wild Robot", html)

    def test_full_house_tier_states_the_guest_cap_and_size(self):
        html = self.client.get(reverse("sponsor")).content.decode()
        self.assertIn("first 100 guests", html)
        self.assertIn("Medium", html)

    def test_filter_choices_come_from_available_titles(self):
        context = self.client.get(reverse("sponsor")).context
        self.assertIn("PG", context["ratings"])
        self.assertIn(1970, context["decades"])
        self.assertIn(2020, context["decades"])


class SponsorSitemapTests(TestCase):
    def test_sponsor_is_in_the_sitemap(self):
        html = self.client.get("/sitemap.xml").content.decode()
        self.assertIn("/sponsor/", html)

    def test_sponsor_is_in_the_site_navigation(self):
        # nav.html loops SITE_CONFIG["navigation"]; the trailing slash matters
        # because a bare /sponsor would 301 on every click.
        html = self.client.get("/").content.decode()
        self.assertIn('href="/sponsor/"', html)
