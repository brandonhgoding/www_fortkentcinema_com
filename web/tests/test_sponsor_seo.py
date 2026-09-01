"""SEO work on /sponsor/: discovery, structured data, the card, and weight.

The page was already well-formed at the head level — title, description,
canonical, og overrides and heading order were all correct. What it was
missing was everything that tells a search engine *what it is*: it declared
nothing about the service it sells, carried the site-wide social card, and
had one internal link sitewide. It also shipped 56KB of hidden <option>
elements to every visitor, more than half its HTML.
"""

import datetime
import html as html_lib
import json
import re

from cinema.models import SponsorshipInquiry, Studio, StudioTitle
from django.test import TestCase
from django.urls import reverse

from web.constants import SPONSORSHIP_FAQ, SPONSORSHIP_TIERS


def jsonld_blocks(html):
    return [
        json.loads(block)
        for block in re.findall(
            r'<script type="application/ld\+json">(.*?)</script>', html, re.S
        )
    ]


def block_of_type(html, wanted):
    for block in jsonld_blocks(html):
        if block.get("@type") == wanted:
            return block
    return None


def hrefs(html):
    return re.findall(r'<a[^>]+href="([^"]+)"', html)


class SponsorStructuredDataTests(TestCase):
    """base.html's MovieTheater says the cinema exists. It says nothing about
    the thing this page sells, which is a priced service with three levels."""

    def setUp(self) -> None:
        self.html = self.client.get(reverse("sponsor")).content.decode()

    def test_every_jsonld_block_is_valid_json(self):
        # One malformed block is one Google discards silently. Parsing them
        # all is the only assertion that catches a stray comma from a
        # {% for %} loop.
        self.assertGreaterEqual(len(jsonld_blocks(self.html)), 4)

    def test_emits_a_service_block(self):
        service = block_of_type(self.html, "Service")
        self.assertIsNotNone(service, "no Service block")
        self.assertEqual(service["serviceType"], "Film sponsorship")
        self.assertIn("/sponsor/", service["url"])

    def test_service_offers_every_tier(self):
        offers = block_of_type(self.html, "Service")["offers"]
        self.assertEqual(
            [offer["name"] for offer in offers],
            [tier["name"] for tier in SPONSORSHIP_TIERS],
        )

    def test_offers_quote_a_starting_price_not_a_firm_one(self):
        """Every tier on the page is quoted "from $X", and the tier note says
        outright that the final number depends on the title. A flat `price`
        would be a quote we do not honour."""
        for offer, tier in zip(
            block_of_type(self.html, "Service")["offers"], SPONSORSHIP_TIERS
        ):
            spec = offer["priceSpecification"]
            self.assertNotIn("price", offer, offer["name"])
            self.assertEqual(spec["minPrice"], tier["price"])
            self.assertEqual(spec["priceCurrency"], "USD")

    def test_service_names_who_and_where_it_is_for(self):
        # Neither is in the title or the H1, and both are what a business in
        # the valley would actually type.
        service = block_of_type(self.html, "Service")
        self.assertEqual(service["audience"]["@type"], "BusinessAudience")
        areas = json.dumps(service["areaServed"])
        self.assertIn("Fort Kent", areas)
        self.assertIn("Aroostook", areas)
        self.assertIn("St. John Valley", areas)

    def test_emits_breadcrumb_trail(self):
        crumbs = block_of_type(self.html, "BreadcrumbList")["itemListElement"]
        self.assertEqual([c["position"] for c in crumbs], [1, 2])
        self.assertEqual(crumbs[-1]["name"], "Sponsor a Film")
        self.assertTrue(crumbs[-1]["item"].endswith("/sponsor/"))

    def test_emits_faq_block_for_every_question(self):
        faq = block_of_type(self.html, "FAQPage")["mainEntity"]
        self.assertEqual(
            [q["name"] for q in faq],
            [item["question"] for item in SPONSORSHIP_FAQ],
        )

    def test_every_marked_up_answer_is_visible_on_the_page(self):
        """Google penalises FAQ markup whose answers are not on the page, and
        it is a real risk here: the schema and the <dl> are separate template
        blocks that could drift."""
        body = re.sub(
            r"<script.*?</script>", "", self.html, flags=re.S
        )
        # unescape, because Django renders the apostrophes in these answers
        # as &#x27; — the text is on the page, just not byte-identical to the
        # constant the JSON-LD block escapes differently.
        text = html_lib.unescape(
            re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", body))
        )
        for item in SPONSORSHIP_FAQ:
            self.assertIn(re.sub(r"\s+", " ", item["answer"]), text)


class SponsorInternalLinkTests(TestCase):
    """The nav's "More" dropdown was the only link to /sponsor/ sitewide —
    the same one-link position /history/ was in before it got a footer link
    and a homepage CTA. A page nothing links to is a page Google will not
    rank."""

    def test_footer_links_to_sponsor_from_a_page_that_is_not_home(self):
        # Scoped to the <footer>. The nav dropdown renders on every page too,
        # so an unscoped assertion passes without the footer link existing.
        html = self.client.get(reverse("rentals")).content.decode()
        footer = re.search(r"<footer\b.*?</footer>", html, re.S)
        self.assertIsNotNone(footer, "no footer on the page")
        self.assertIn("/sponsor/", hrefs(footer.group(0)))

    def test_homepage_body_promotes_the_sponsor_page(self):
        response = self.client.get("/")
        self.assertTemplateUsed(response, "partials/cta_sponsor.html")

    def test_homepage_links_to_sponsor_from_more_than_just_the_nav(self):
        count = hrefs(self.client.get("/").content.decode()).count("/sponsor/")
        self.assertGreaterEqual(count, 2, "nav dropdown is still the only link")

    def test_faq_links_out_to_private_rentals(self):
        """The one FAQ answer that points somewhere else. A reader who wants
        the room to themselves should land on /rentals/, not send a
        sponsorship inquiry we have to redirect."""
        html = self.client.get(reverse("sponsor")).content.decode()
        faq = re.search(
            r'<section class="sponsor-faq".*?</section>', html, re.S
        )
        self.assertIsNotNone(faq, "no FAQ section")
        self.assertIn("/rentals/", hrefs(faq.group(0)))


class SponsorSocialCardTests(TestCase):
    """The page carried static/img/og-image.jpg, the site-wide card, which
    says nothing about sponsorship."""

    CARD = "img/og-sponsor.jpg"

    def setUp(self) -> None:
        self.html = self.client.get(reverse("sponsor")).content.decode()

    def _og_image(self):
        return re.search(
            r'<meta property="og:image" content="([^"]+)"', self.html
        ).group(1)

    def test_og_image_is_the_pages_own_card(self):
        self.assertIn(self.CARD, self._og_image())

    def test_og_image_is_not_the_site_default(self):
        self.assertNotIn("img/og-image.jpg", self._og_image())

    def test_og_image_is_absolute(self):
        # Facebook and X both drop a relative og:image on the floor.
        self.assertTrue(self._og_image().startswith("http"), self._og_image())

    def test_the_card_file_is_fetchable_and_correctly_sized(self):
        """A crawler that times out fetching the card shows no preview."""
        from pathlib import Path

        from django.conf import settings
        from PIL import Image

        path = Path(settings.BASE_DIR) / "static" / self.CARD
        self.assertTrue(path.exists(), f"{path} is missing")
        self.assertLess(path.stat().st_size, 300_000)
        with Image.open(path) as im:
            self.assertEqual(im.size, (1200, 630))

    def test_the_committed_card_still_matches_its_source(self):
        """It is generated, not drawn — so it must not be edited by hand or
        left behind when promo.py changes. `render_promo_cards` is
        deterministic, so this is a byte comparison."""
        from pathlib import Path

        from django.conf import settings

        from cinema.social_cards import promo

        path = Path(settings.BASE_DIR) / "static" / self.CARD
        self.assertEqual(
            path.read_bytes(),
            promo.to_jpeg(promo.render_sponsor_card()),
            "static/img/og-sponsor.jpg is stale — run "
            "`manage.py render_promo_cards`",
        )


class SponsorDeferredFilmListTests(TestCase):
    """The inquiry form's film <select> was ~1,140 <option> elements — 56KB,
    more than half of /sponsor/'s HTML — shipped to everyone before anyone
    opened the drawer.

    The rule that matters: trimming what gets *rendered* must not weaken what
    gets *validated*.
    """

    @classmethod
    def setUpTestData(cls) -> None:
        cls.studio = Studio.objects.create(
            name="Universal Pictures", slug="universal"
        )
        cls.titles = [
            StudioTitle.objects.create(
                studio=cls.studio,
                original_title=f"TITLE {n:03d}",
                title=f"Title {n:03d}",
                release_date=datetime.date(1990, 1, 1),
                mpa_rating="PG",
                runtime_minutes=100,
            )
            for n in range(30)
        ]
        cls.hidden = StudioTitle.objects.create(
            studio=cls.studio, original_title="HIDDEN", title="Hidden",
            release_date=datetime.date(2020, 1, 1), is_available=False,
        )

    def _film_select(self, html):
        return re.search(
            r'<select[^>]*name="studio_title".*?</select>', html, re.S
        ).group(0)

    def test_the_page_no_longer_ships_the_whole_catalog(self):
        html = self.client.get(reverse("sponsor")).content.decode()
        # Only "Not sure yet" survives; the 30 titles do not.
        self.assertEqual(self._film_select(html).count("<option"), 1)

    def test_the_select_asks_for_the_rest_on_demand(self):
        select = self._film_select(
            self.client.get(reverse("sponsor")).content.decode()
        )
        self.assertIn(reverse("sponsor_films"), select)
        self.assertIn("hx-swap=\"innerHTML\"", select)

    def test_the_options_endpoint_serves_every_available_title(self):
        html = self.client.get(reverse("sponsor_films")).content.decode()
        # Every available title, plus the empty option the innerHTML swap
        # has to put back.
        self.assertEqual(html.count("<option"), len(self.titles) + 1)
        self.assertIn("Title 029", html)
        self.assertNotIn("Hidden", html)

    def test_the_options_endpoint_is_noindex(self):
        """A bare fragment with no <head> to hold a meta tag. /sponsor/ is
        the page that should rank."""
        response = self.client.get(reverse("sponsor_films"))
        self.assertEqual(
            response["X-Robots-Tag"], "noindex, nofollow"
        )

    def test_the_options_endpoint_is_not_in_the_sitemap(self):
        xml = self.client.get("/sitemap.xml").content.decode()
        self.assertNotIn("/sponsor/films", xml)

    def test_no_javascript_visitors_can_still_get_the_whole_list(self):
        html = self.client.get(
            reverse("sponsor"), {"films": "all"}
        ).content.decode()
        self.assertEqual(
            self._film_select(html).count("<option"), len(self.titles) + 1
        )

    def test_the_heavy_twin_stays_out_of_the_index(self):
        html = self.client.get(
            reverse("sponsor"), {"films": "all"}
        ).content.decode()
        self.assertIn('name="robots" content="noindex, follow"', html)

    def test_the_light_page_is_still_indexable(self):
        html = self.client.get(reverse("sponsor")).content.decode()
        self.assertIn('name="robots" content="index, follow"', html)

    def test_a_link_can_still_name_a_film_without_javascript(self):
        chosen = self.titles[29]
        html = self.client.get(
            reverse("sponsor"), {"film": chosen.pk}
        ).content.decode()
        select = self._film_select(html)
        self.assertIn(f'value="{chosen.pk}"', select)
        self.assertIn("Title 029", select)

    def test_an_unrendered_film_is_still_accepted_on_post(self):
        """The whole point of the change: the option was not in the HTML, but
        it is still a real, available title and the form must take it."""
        chosen = self.titles[29]
        response = self.client.post(reverse("sponsor_inquire"), {
            "business_name": "A.H. Custom Carpentry",
            "contact_name": "Andrew",
            "email": "andrew@example.com",
            "phone": "", "tier": "", "message": "", "website": "",
            "studio_title": chosen.pk,
        })
        self.assertEqual(response.status_code, 302)
        self.assertEqual(
            SponsorshipInquiry.objects.get().studio_title, chosen
        )

    def test_an_unavailable_film_is_still_rejected_on_post(self):
        """Trimming the rendered choices must not have turned validation off.
        `queryset` is what rejects this, and it is deliberately untouched."""
        response = self.client.post(reverse("sponsor_inquire"), {
            "business_name": "A.H. Custom Carpentry",
            "contact_name": "Andrew",
            "email": "andrew@example.com",
            "phone": "", "tier": "", "message": "", "website": "",
            "studio_title": self.hidden.pk,
        })
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.context["form"].errors.get("studio_title"))

    def test_a_forged_pk_is_still_rejected_on_post(self):
        response = self.client.post(reverse("sponsor_inquire"), {
            "business_name": "A.H. Custom Carpentry",
            "contact_name": "Andrew",
            "email": "andrew@example.com",
            "phone": "", "tier": "", "message": "", "website": "",
            "studio_title": 10_000_000,
        })
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.context["form"].errors.get("studio_title"))

    def test_a_validation_error_keeps_the_film_that_was_chosen(self):
        """The error re-render is deferred too, so the chosen option has to be
        put back explicitly or the reader silently loses their pick."""
        chosen = self.titles[29]
        response = self.client.post(reverse("sponsor_inquire"), {
            "business_name": "",  # required — forces the re-render
            "contact_name": "Andrew",
            "email": "andrew@example.com",
            "phone": "", "tier": "", "message": "", "website": "",
            "studio_title": chosen.pk,
        })
        self.assertEqual(response.status_code, 200)
        select = self._film_select(response.content.decode())
        self.assertIn(f'value="{chosen.pk}"', select)


class SponsorFaqTests(TestCase):
    def setUp(self) -> None:
        self.html = self.client.get(reverse("sponsor")).content.decode()

    def test_the_questions_are_rendered_for_readers_too(self):
        for item in SPONSORSHIP_FAQ:
            self.assertIn(item["question"], self.html)

    def test_the_faq_is_a_definition_list_not_a_collapsed_accordion(self):
        """Every answer is short, and collapsing them would hide the page's
        only long-tail text behind a click."""
        faq = re.search(
            r'<section class="sponsor-faq".*?</section>', self.html, re.S
        ).group(0)
        self.assertIn("<dl", faq)
        self.assertNotIn("<details", faq)
        self.assertEqual(faq.count("<dt"), len(SPONSORSHIP_FAQ))
        self.assertEqual(faq.count("<dd"), len(SPONSORSHIP_FAQ))

    def test_the_faq_heading_sits_under_the_h1(self):
        # h2, not h1: one H1 per page, and it is "SPONSOR A FILM".
        self.assertIn('<h2 class="sponsor-faq__title"', self.html)


class StaticSitemapLastmodTests(TestCase):
    """The static sitemap carried no <lastmod> at all, so nothing told Google
    that a page it already had a copy of was worth re-fetching.

    The dates are hand-maintained, which means the risk is not that they are
    wrong today but that they rot. These tests are the guard rail.
    """

    def _urls(self):
        xml = self.client.get("/sitemap.xml").content.decode()
        return dict(
            re.findall(
                r"<url><loc>(.*?)</loc>.*?<lastmod>(.*?)</lastmod>", xml
            )
        )

    def test_every_static_page_has_a_maintained_date(self):
        """Adding a page to items() without dating it is the way this decays:
        the page ships with no lastmod and nobody notices."""
        from web.sitemaps import STATIC_PAGE_LASTMOD, StaticViewSitemap

        undated = [
            name
            for name in StaticViewSitemap().items()
            if name not in STATIC_PAGE_LASTMOD
        ]
        self.assertEqual(
            undated, [], f"add these to STATIC_PAGE_LASTMOD: {undated}"
        )

    def test_no_date_is_in_the_future(self):
        """A future date is the clearest possible tell that these are being
        set by hand rather than observed, and it is what makes Google stop
        trusting lastmod across the whole site."""
        from web.sitemaps import STATIC_PAGE_LASTMOD

        today = datetime.date.today()
        ahead = {
            name: date
            for name, date in STATIC_PAGE_LASTMOD.items()
            if date > today
        }
        self.assertEqual(ahead, {}, f"dated in the future: {ahead}")

    def test_the_sitemap_actually_emits_them(self):
        urls = self._urls()
        sponsor = [u for u in urls if u.endswith("/sponsor/")]
        self.assertEqual(len(sponsor), 1, "sponsor missing from the sitemap")
        self.assertTrue(urls[sponsor[0]], "sponsor has an empty lastmod")

    def test_a_data_driven_page_beats_its_template_date(self):
        """/blog/ moves when a post lands, with nobody touching the template.
        A fixed date would go stale the same day."""
        from blog.models import BlogAuthor, BlogCategory, BlogPost
        from web.sitemaps import STATIC_PAGE_LASTMOD, StaticViewSitemap

        future = datetime.date.today()
        BlogPost.objects.create(
            title="A new post",
            post_date=future,
            content="x",
            author=BlogAuthor.objects.create(
                first_name="Brandon", last_name="Goding"
            ),
            category=BlogCategory.objects.create(name="News"),
        )
        self.assertEqual(StaticViewSitemap().lastmod("blog_list"), future)
        self.assertGreater(future, STATIC_PAGE_LASTMOD["blog_list"])
