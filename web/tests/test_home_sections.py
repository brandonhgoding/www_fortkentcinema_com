"""Home page structure: section order, showtime chips, hours, empty states.

The audit found four things wrong on the page that carries ~99% of this
site's search clicks:

  * ornament dividers emitted unconditionally, so a self-expiring CTA left
    two of them stacked, and a hidden section left one leading or trailing;
  * showtimes marked up as <button> with no handler anywhere and no online
    ticket path in the project at all;
  * SITE_CONFIG["hours"] rendered in zero templates (since replaced by
    "opens before every show" — the fixed hours contradicted the schedule);
  * empty states that were a flat sentence or a blank void.

The dividers were then removed outright rather than placed correctly, and
the {% section %} tag went with them — with no seam to emit it did nothing
a bare {% include %} does not. Sections are separated by their alternating
grounds. What survives here is the ordering guarantee.
"""

import datetime
import json
import re
from pathlib import Path
from unittest import mock

from django.conf import settings
from django.test import TestCase
from django.urls import reverse

from web.constants import SITE_CONFIG, TICKET_PRICES

SECTION_MARKERS = (
    "hero",
    "now-showing",
    "coming-soon",
)


def main_content(html):
    return html.split('<main id="main-content">', 1)[1].split("</main>", 1)[0]


def section_sequence(html):
    """The order the page's top-level sections appear in."""
    pattern = r'(?:class|id)="(%s)"' % "|".join(SECTION_MARKERS)
    seq = [m.group(1) for m in re.finditer(pattern, main_content(html))]
    # coming-soon is both a class and an id on the same <section>
    return [m for i, m in enumerate(seq) if m not in seq[:i]]


def movie(**over):
    base = {
        "id": "1",
        "title": "Dune",
        "rating": "PG-13",
        "runtime": "2h 35min",
        "genre": "Sci-fi",
        "poster": "d.jpg",
        "youtube_id": "abc",
        "showtimes": {"2999-01-15": [{"time": "6:00 PM", "captions": "", "captions_label": ""}, {"time": "9:00 PM", "captions": "", "captions_label": ""}]},
    }
    base.update(over)
    return base


def _time(pk, time, iso):
    return {
        "showtime_id": pk, "time": time, "iso": iso,
        "captions": "", "captions_label": "",
    }


def hero_film(**over):
    """A film as get_hero_films() shapes it, for mocking the hero."""
    base = {
        "id": "1",
        "showtime_id": 1,
        "title": "Dune",
        "rating": "PG-13",
        "runtime": "2h 35min",
        "description": "",
        "poster": "d.jpg",
        "backdrop": "",
        "date": "2999-01-15",
        "time": "6:00 PM",
        "youtube_id": "abc",
        "language_label": "",
        "upcoming": [
            {
                "key": "2999-01-15",
                "times": [
                    _time(1, "6:00 PM", "2999-01-15T18:00:00-05:00"),
                    _time(2, "9:00 PM", "2999-01-15T21:00:00-05:00"),
                ],
            }
        ],
    }
    base.update(over)
    return base


class SectionCompositionTests(TestCase):
    """The page is a plain list of sections now."""

    def home(self):
        return self.client.get(reverse("home")).content.decode()

    @mock.patch("web.views.get_coming_soon", return_value=[])
    @mock.patch("web.views.get_hero_films", return_value=[])
    def test_sections_appear_once_each_in_order(self, _ns, _cs):
        seq = section_sequence(self.home())
        self.assertEqual(
            seq, sorted(set(seq), key=seq.index), "a section rendered twice: %s" % seq
        )
        self.assertEqual(seq[0], "now-showing")

    @mock.patch("web.views.get_coming_soon", return_value=[])
    @mock.patch("web.views.get_hero_films", return_value=[])
    def test_section_order_ends_with_coming_soon(self, _ns, _cs):
        seq = section_sequence(self.home())
        self.assertEqual(
            seq,
            [
                "now-showing",
                "coming-soon",
            ],
        )


class ShowtimeChipTests(TestCase):
    """There is no online ticket path in this project, so a <button> here
    promised a purchase that cannot happen."""

    @mock.patch("web.views.get_coming_soon", return_value=[])
    @mock.patch("web.views.get_hero_films")
    def test_showtimes_are_spans_not_buttons(self, ns, _cs):
        ns.return_value = [hero_film()]
        html = self.client.get(reverse("home")).content.decode()
        # The hero's row renders both times.
        self.assertEqual(html.count('<span class="showtime">'), 2)
        self.assertIn('<span class="showtime">6:00 PM</span>', html)


class FooterHoursTests(TestCase):
    """The box office has no fixed weekly hours: it opens ahead of each show.

    A fixed table (Wednesday - Thursday, Saturday & Sunday) contradicted the
    schedule beside it — Friday Heckle Night, Tuesday shows, an 11 AM Saturday
    matinee — so the footer now says the one thing that is always true.
    """

    def footer(self, path="/"):
        html = self.client.get(path).content.decode()
        match = re.search(r"<footer\b.*?</footer>", html, re.S)
        self.assertIsNotNone(match, "no footer on the page")
        return match.group(0)

    def test_footer_says_the_box_office_opens_before_showtime(self):
        footer = self.footer()
        minutes = SITE_CONFIG["box_office"]["opens_before_show_minutes"]
        self.assertIn(f"Box office opens {minutes} minutes before showtime", footer)

    def test_hours_are_sitewide_not_just_the_home_page(self):
        minutes = SITE_CONFIG["box_office"]["opens_before_show_minutes"]
        self.assertIn(
            f"opens {minutes} minutes before showtime",
            self.footer(reverse("rentals")),
        )


class TheaterSchemaTests(TestCase):
    def theater(self, path="/"):
        html = self.client.get(path).content.decode()
        for raw in re.findall(
            r'<script type="application/ld\+json">\s*(.*?)\s*</script>', html, re.S
        ):
            block = json.loads(raw)
            if block.get("@type") == "MovieTheater":
                return block
        self.fail("no MovieTheater block")

    def test_block_is_still_valid_json(self):
        self.assertEqual(self.theater()["@type"], "MovieTheater")

    def test_new_keys_are_present(self):
        block = self.theater()
        for key in ("image", "hasMap"):
            self.assertIn(key, block)

    def test_has_map_points_at_the_configured_address(self):
        self.assertIn("Hall+Street", self.theater()["hasMap"])

    def test_image_is_absolute(self):
        self.assertRegex(self.theater()["image"], r"^https?://")

    def test_telephone_is_e164(self):
        """schema.org and Google's validator expect the international form;
        the display form stays on the page."""
        self.assertEqual(self.theater()["telephone"], "+12072315287")

    def test_e164_and_display_phone_are_the_same_number(self):
        cinema = SITE_CONFIG["cinema"]
        self.assertEqual(
            cinema["phone_e164"], "+1" + re.sub(r"\D", "", cinema["phone"])
        )

    def test_price_range_is_the_real_ticket_range(self):
        """"$$" is a vague tier; the page states real prices, from the
        cheapest ticket to adult admission."""
        with mock.patch.dict(TICKET_PRICES, adult=9, senior=7, child=5, matinee=3):
            self.assertEqual(self.theater()["priceRange"], "$3 - $9")

    def test_screen_count_and_capacity_come_from_the_config(self):
        """Two screens, 100 seats each (owner, 2026-10-15). Listed so the
        directories that say one screen have something to be corrected
        against."""
        screens = SITE_CONFIG["cinema"]["screens"]
        block = self.theater()
        self.assertEqual(block["screenCount"], len(screens))
        self.assertEqual(
            block["maximumAttendeeCapacity"], sum(s["seats"] for s in screens)
        )

    def test_logo_is_an_absolute_png_that_ships(self):
        logo = self.theater()["logo"]
        self.assertRegex(logo, r"^https?://.+\.png$")
        name = logo.rsplit("/static/", 1)[1]
        self.assertTrue((Path(settings.BASE_DIR) / "static" / name).exists())


class TelLinkTests(TestCase):
    """Every tel: link dials SITE_CONFIG's number. They were typed by hand on
    six pages, and the footer built its own by stripping punctuation, which
    left off the country code."""

    PAGES = ["/", "/rentals/", "/advertise/", "/no-such-page/"]

    @mock.patch("web.views.get_calendar_month", return_value={})
    @mock.patch("web.views.get_coming_soon", return_value=[])
    @mock.patch("web.views.get_hero_films", return_value=[])
    def test_every_tel_link_comes_from_the_config(self, *_):
        with mock.patch.dict(SITE_CONFIG["cinema"], phone_e164="+19995550100",
                             phone="(999) 555-0100"):
            for path in self.PAGES:
                with self.subTest(path=path):
                    html = self.client.get(path).content.decode()
                    links = re.findall(r'href="tel:([^"]*)"', html)
                    self.assertTrue(links, "no tel: link")
                    self.assertEqual(set(links), {"+19995550100"})
                    self.assertNotIn("231-5287", html)


class EmptyStateTests(TestCase):
    @mock.patch("web.views.get_coming_soon", return_value=[])
    @mock.patch("web.views.get_hero_films", return_value=[])
    def test_now_showing_empty_state_offers_somewhere_to_go(self, _ns, _cs):
        html = self.client.get(reverse("home")).content.decode()
        # Through the links list: the signup form's honeypot has its own </div>.
        empty = re.search(r'<div class="no-showtimes">.*?</ul>', html, re.S).group(0)
        self.assertIn(SITE_CONFIG["social"]["facebook"], empty)
        self.assertIn("#coming-soon", empty)

    @mock.patch("web.views.get_coming_soon", return_value=[])
    @mock.patch("web.views.get_hero_films", return_value=[])
    def test_coming_soon_empty_state_is_not_a_blank_void(self, _ns, _cs):
        html = self.client.get(reverse("home")).content.decode()
        self.assertIn('class="coming-empty"', html)
        empty = html.split('class="coming-empty"', 1)[1].split("</div>", 1)[0]
        self.assertIn(SITE_CONFIG["social"]["facebook"], empty)

    @mock.patch("web.views.get_coming_soon")
    @mock.patch("web.views.get_hero_films")
    def test_empty_states_stay_out_of_the_way_when_there_is_content(self, ns, cs):
        ns.return_value = [hero_film()]
        cs.return_value = [
            {
                "id": "5",
                "title": "Wicked",
                "release_date": "November 22",
                "genre": "",
                "poster": "w.jpg",
                "youtube_id": "",
                "films": [],
                "start_date": "2999-11-22",
            }
        ]
        html = self.client.get(reverse("home")).content.decode()
        self.assertNotIn("no-showtimes", html)
        self.assertNotIn("coming-empty", html)


class ScreeningEventSchemaTests(TestCase):
    """The home page says what is playing, not only that the cinema exists.

    One schema.org ScreeningEvent per upcoming showtime the Now Showing
    section renders, inside an @graph so the existing jsonld() helpers,
    which call .get("@type") on every block, keep working.
    """

    def setUp(self):
        from cinema.models import Engagement, EngagementFilm, Film, Screen, Showtime

        self.screen = Screen.objects.create(name="Screen 1", capacity=100)
        self.film = Film.objects.create(
            title="Dune", rating="PG-13", poster_url="http://p/d.jpg"
        )
        self.today = datetime.date.today()
        self.eng = Engagement.objects.create(
            screen=self.screen,
            start_date=self.today - datetime.timedelta(days=1),
            end_date=self.today + datetime.timedelta(days=2),
            status="CONFIRMED",
        )
        EngagementFilm.objects.create(engagement=self.eng, film=self.film, position=1)
        self.Showtime = Showtime

    def showtime(self, day_offset, hour):
        from django.utils import timezone

        d = self.today + datetime.timedelta(days=day_offset)
        return self.Showtime.objects.create(
            engagement=self.eng,
            starts_at=timezone.make_aware(datetime.datetime(d.year, d.month, d.day, hour)),
        )

    def events(self):
        html = self.client.get(reverse("home")).content.decode()
        for raw in re.findall(
            r'<script type="application/ld\+json">\s*(.*?)\s*</script>', html, re.S
        ):
            block = json.loads(raw)
            if "@graph" in block:
                return [n for n in block["@graph"] if n.get("@type") == "ScreeningEvent"]
        return None

    def test_one_event_per_upcoming_showtime_with_the_visible_facts(self):
        from web.constants import TICKET_PRICES
        from web.services.cinema_data import CINEMA_TZ

        first = self.showtime(1, 16)
        self.showtime(1, 19)
        self.showtime(2, 19)
        events = self.events()
        self.assertIsNotNone(events, "no @graph block on the home page")
        self.assertEqual(len(events), 3)
        ev = events[0]
        self.assertEqual(ev["name"], "Dune at Fort Kent Cinema")
        self.assertEqual(ev["startDate"], first.starts_at.astimezone(CINEMA_TZ).isoformat())
        self.assertEqual(ev["location"]["@id"], "https://www.fortkentcinema.com/#theater")
        self.assertEqual(ev["location"]["address"]["streetAddress"],
                         SITE_CONFIG["cinema"]["address"]["street"])
        self.assertEqual(ev["workPresented"]["name"], "Dune")
        self.assertEqual(ev["workPresented"]["image"], "http://p/d.jpg")
        self.assertEqual(ev["workPresented"]["contentRating"], "PG-13")
        self.assertEqual(ev["offers"]["lowPrice"], str(min(
            TICKET_PRICES[t] for t in ("adult", "senior", "child", "matinee"))))
        self.assertEqual(ev["offers"]["highPrice"], str(TICKET_PRICES["adult"]))
        self.assertEqual(ev["offers"]["priceCurrency"], "USD")

    def test_past_showtimes_of_a_running_engagement_are_not_events(self):
        """Advertising a screening that already happened is wrong, and the
        chips do not show it either."""
        self.showtime(-1, 19)
        self.showtime(1, 19)
        self.assertEqual(len(self.events()), 1)

    def test_theater_block_carries_the_id_the_events_point_at(self):
        html = self.client.get(reverse("home")).content.decode()
        self.assertIn('"@id": "https://www.fortkentcinema.com/#theater"',
                      html.split("@graph")[0])

    @mock.patch("web.views.get_coming_soon", return_value=[])
    @mock.patch("web.views.get_hero_films", return_value=[])
    def test_no_block_when_nothing_is_booked(self, _ns, _cs):
        self.assertIsNone(self.events())

    @mock.patch("web.views.get_coming_soon", return_value=[])
    @mock.patch("web.views.get_hero_films")
    def test_showtimes_without_an_iso_start_are_skipped_not_fatal(self, ns, _cs):
        """Older fixtures and callers hand the view time dicts with no iso;
        an event with no startDate is worse than no event."""
        film = hero_film()
        for time in film["upcoming"][0]["times"]:
            del time["iso"]
        ns.return_value = [film]
        self.assertEqual(self.client.get(reverse("home")).status_code, 200)
        self.assertIsNone(self.events())


class TheaterFormerNameTests(TestCase):
    """Showtime directories still carry the old name, "The Century Theater",
    and the building is still called that in town. The MovieTheater block
    says so, so a machine can tie the two names to one business instead of
    guessing they are neighbours."""

    def theater(self):
        html = self.client.get("/").content.decode()
        for raw in re.findall(
            r'<script type="application/ld\+json">\s*(.*?)\s*</script>', html, re.S
        ):
            block = json.loads(raw)
            if block.get("@type") == "MovieTheater":
                return block
        self.fail("no MovieTheater block")

    def test_former_name_is_an_alternate_name(self):
        self.assertEqual(self.theater()["alternateName"], "The Century Theater")
