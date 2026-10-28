"""Selenium E2E tests for the JS-driven flows (nav mobile menu, blog infinite
scroll, coming-soon calendar toggle).

These tests spin up a real headless Chrome via Selenium 4's Selenium Manager
(which auto-provisions a matching chromedriver). Chrome is not guaranteed to
be installed in every environment `manage.py test` runs in (CI containers,
minimal deploy images, etc.), so the base `SeleniumTestCase.setUpClass`
catches *any* exception from driver startup and turns it into a clean
`unittest.SkipTest` rather than letting the whole suite fail. Nothing in this
module should ever surface as an ERROR/FAIL purely because Chrome/driver is
missing.
"""

import unittest
from unittest import mock

from django.contrib.staticfiles.testing import StaticLiveServerTestCase

from blog.models import BlogAuthor, BlogCategory, BlogPost


def _make_driver():
    from selenium import webdriver
    from selenium.webdriver.chrome.options import Options

    opts = Options()
    opts.add_argument("--headless=new")
    opts.add_argument("--no-sandbox")
    opts.add_argument("--disable-gpu")
    opts.add_argument("--window-size=1280,900")
    return webdriver.Chrome(options=opts)


class SeleniumTestCase(StaticLiveServerTestCase):
    """Base class: starts a real live Django server + headless Chrome.

    If Chrome/chromedriver can't be started for *any* reason (not installed,
    Selenium Manager can't resolve a driver, sandbox restrictions, etc.) the
    whole class is skipped instead of erroring.
    """

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        try:
            cls.driver = _make_driver()
            cls.driver.set_page_load_timeout(30)
        except Exception as exc:  # no browser/driver in this env
            raise unittest.SkipTest(f"Selenium/Chrome unavailable: {exc}")

    @classmethod
    def tearDownClass(cls):
        driver = getattr(cls, "driver", None)
        if driver is not None:
            driver.quit()
        super().tearDownClass()

    def wait(self, timeout=15):
        from selenium.webdriver.support.ui import WebDriverWait

        return WebDriverWait(self.driver, timeout)


class NavMenuE2E(SeleniumTestCase):
    """The mobile nav hamburger menu. This flow touches only the base chrome
    (nav/footer) and doesn't depend on the leprinceos API, so it's the
    must-pass-or-skip flow: it should work in any environment where Chrome is
    available at all.
    """

    @mock.patch("web.views.get_coming_soon", return_value=[])
    @mock.patch("web.views.get_hero_films", return_value=[])
    def test_mobile_menu_toggles(self, _ns, _cs):
        from selenium.webdriver.common.by import By
        from selenium.webdriver.support import expected_conditions as EC

        self.driver.set_window_size(500, 900)  # phone width -> hamburger visible
        self.driver.get(self.live_server_url + "/")

        links = self.wait().until(
            EC.presence_of_element_located((By.CSS_SELECTOR, ".nav-links"))
        )
        self.assertNotIn("nav-links--open", links.get_attribute("class"))

        hamburger = self.wait().until(
            EC.element_to_be_clickable((By.CSS_SELECTOR, ".nav-hamburger"))
        )
        hamburger.click()

        self.wait().until(
            lambda d: "nav-links--open" in links.get_attribute("class")
        )
        self.assertIn("nav-links--open", links.get_attribute("class"))


class BlogPaginationE2E(SeleniumTestCase):
    """Blog listing's numbered pagination. This replaced an HTMX infinite
    scroll, which hid every post past the first page from crawlers — see
    blog/tests/test_indexability.py. Seeds more posts than one page so the
    pagination nav must render and navigate.
    """

    def setUp(self):
        # NOTE: setUpTestData is a django.test.TestCase-only mechanism; this
        # base class is a LiveServerTestCase (-> TransactionTestCase), which
        # never calls it. Seed per-test in setUp instead.
        super().setUp()
        author = BlogAuthor.objects.create(first_name="Jane", last_name="Doe")
        category = BlogCategory.objects.create(name="News")
        for i in range(15):  # > 13, page 1's lead + paginate_by (12)
            BlogPost.objects.create(
                title=f"Post {i}",
                subtitle=f"Subtitle {i}",
                author=author,
                category=category,
                content=f"Body content for post {i}.",
                post_date=f"2026-01-{i + 1:02d}",
            )

    def test_next_link_navigates_to_page_two(self):
        from selenium.webdriver.common.by import By

        self.driver.get(self.live_server_url + "/blog/")

        cards = self.wait().until(
            lambda d: d.find_elements(By.CSS_SELECTOR, ".blog-card") or False
        )
        self.assertEqual(len(cards), 13)  # the lead + PostListView.paginate_by

        next_link = self.driver.find_element(
            By.CSS_SELECTOR, ".blog-pagination a[rel='next']"
        )
        # global.css sets `scroll-behavior: smooth`, so Selenium's own
        # scroll-into-view is still animating when it hit-tests the click.
        # `behavior: 'instant'` overrides it.
        self.driver.execute_script(
            "arguments[0].scrollIntoView({block: 'center', behavior: 'instant'});",
            next_link,
        )
        next_link.click()

        self.wait(15).until(lambda d: "page=2" in d.current_url)
        self.assertEqual(
            len(self.driver.find_elements(By.CSS_SELECTOR, ".blog-card")), 2
        )


class ComingSoonCalendarE2E(SeleniumTestCase):
    """The ComingSoon section's grid/calendar view toggle. Clicking the
    calendar button flips Alpine's `view` state (revealing the calendar
    container) which in turn lazy-loads the HTMX calendar-month fragment.

    `get_calendar_month` is mocked so this flow doesn't depend on the
    leprinceos API being reachable in the test environment - the toggle +
    HTMX wiring is what's under test, not the external data.
    """

    @mock.patch("web.views.get_calendar_month", return_value={})
    @mock.patch("web.views.get_coming_soon", return_value=[])
    @mock.patch("web.views.get_hero_films", return_value=[])
    def test_calendar_toggle_loads_calendar_fragment(self, _ns, _cs, _cal):
        from selenium.webdriver.common.by import By
        from selenium.webdriver.support import expected_conditions as EC

        self.driver.set_window_size(1280, 900)
        self.driver.get(self.live_server_url + "/")

        calendar_btn = self.wait().until(
            EC.presence_of_element_located(
                (By.CSS_SELECTOR, ".coming-view-btn[aria-label='Calendar view']")
            )
        )
        self.driver.execute_script(
            "arguments[0].scrollIntoView({block: 'center'});", calendar_btn
        )
        # A plain WebDriver .click() can be intercepted by the fixed nav bar
        # or other overlapping chrome depending on where scrollIntoView lands
        # the element; a JS click is robust to that and still exercises the
        # real Alpine @click handler (Alpine listens via addEventListener,
        # which JS-dispatched clicks trigger the same as a real click).
        self.driver.execute_script("arguments[0].click();", calendar_btn)

        self.wait(15).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, ".coming-calendar"))
        )
        self.assertTrue(
            self.driver.find_elements(By.CSS_SELECTOR, ".coming-calendar")
        )

        # A screen reader hears which view is on, not just two icon buttons.
        grid_btn = self.driver.find_element(
            By.CSS_SELECTOR, ".coming-view-btn[aria-label='Grid view']"
        )
        self.assertEqual(calendar_btn.get_attribute("aria-pressed"), "true")
        self.assertEqual(grid_btn.get_attribute("aria-pressed"), "false")


class AnalyticsClickE2E(SeleniumTestCase):
    """The tracked-click path end to end in a real browser: a click on a real
    element must reach gtag with the right event name and params.

    The vitest suite exercises analytics.js in isolation; this proves the module
    actually loads on the page and the data-track attributes are wired to it.

    gtag is stubbed to capture calls, because GA_MEASUREMENT_ID is unset in
    tests (so the real gtag never loads) — and because a test has no business
    sending hits to production analytics.
    """

    def test_facebook_click_reaches_gtag(self):
        # Was the home page's gift-card link until that card came out
        # (2026-10-13). The Facebook link in Now Showing's empty state is the
        # same shape — tracked, target=_blank — and the test database has no
        # showtimes, so it is always on the page here.
        from selenium.webdriver.common.by import By

        self.driver.get(self.live_server_url + "/")

        # Stub gtag before clicking; analytics.js reads window.gtag at call time.
        self.driver.execute_script(
            "window.__events = [];"
            "window.gtag = function () { window.__events.push([...arguments]); };"
        )

        link = self.wait().until(
            lambda d: d.find_element(By.CSS_SELECTOR, '[data-track="facebook_click"]')
        )
        # The link opens Facebook in a new tab (target=_blank), so this page stays
        # put and we can read what was captured.
        self.driver.execute_script(
            "arguments[0].scrollIntoView({block: 'center', behavior: 'instant'});", link
        )
        link.click()

        events = self.wait().until(
            lambda d: d.execute_script("return window.__events;") or False
        )
        self.assertEqual(events[0][0], "event")
        self.assertEqual(events[0][1], "facebook_click")


class TrailerDialogE2E(SeleniumTestCase):
    """The trailer overlays on the film hero and Coming Soon behave as modal
    dialogs: announced as modal, focus goes to Close on open, stays inside
    while open, Escape closes, and focus returns to the poster that opened it.
    Without that a keyboard user is left on a poster behind the overlay, and a
    screen reader can wander the page underneath."""

    SECTIONS = {
        "now showing": (".hero-film__poster-wrap--playable", ".now-trailer-overlay",
                        ".now-trailer-close"),
        "coming soon": (".coming-movie-poster--playable", ".coming-trailer-overlay",
                        ".coming-trailer-close"),
    }

    def setUp(self):
        import datetime

        from cinema.models import Showtime
        from django.utils import timezone

        from web.tests.test_cinema_data import (
            aware, make_engagement, make_film, make_screen,
        )

        screen = make_screen()
        today = timezone.localdate()
        tomorrow = today + datetime.timedelta(days=1)
        now = make_engagement(
            screen, [make_film("Dune", poster_url="http://p/d.jpg", youtube_id="yt1")],
            start=today, end=today + datetime.timedelta(days=3),
        )
        Showtime.objects.create(
            engagement=now,
            starts_at=aware(tomorrow.year, tomorrow.month, tomorrow.day, 19),
        )
        make_engagement(
            screen, [make_film("Alpha", poster_url="http://p/a.jpg", youtube_id="yta")],
            start=today + datetime.timedelta(days=10),
            end=today + datetime.timedelta(days=12),
        )

    def active_matches(self, selector):
        return self.driver.execute_script(
            "return document.activeElement.matches(arguments[0]);", selector
        )

    @mock.patch("web.views.get_calendar_month", return_value={})
    def test_trailer_overlays_are_modal_dialogs(self, _cal):
        from selenium.webdriver.common.by import By
        from selenium.webdriver.common.keys import Keys

        self.driver.set_window_size(1280, 900)
        self.driver.get(self.live_server_url + "/")

        for name, (opener_sel, overlay_sel, close_sel) in self.SECTIONS.items():
            with self.subTest(section=name):
                opener = self.wait().until(
                    lambda d: d.find_element(By.CSS_SELECTOR, opener_sel)
                )
                overlay = self.driver.find_element(By.CSS_SELECTOR, overlay_sel)
                self.assertEqual(overlay.get_attribute("aria-modal"), "true")

                self.driver.execute_script(
                    "arguments[0].scrollIntoView({block: 'center', behavior: 'instant'});"
                    "arguments[0].focus();",
                    opener,
                )
                opener.send_keys(Keys.ENTER)
                self.wait(5).until(lambda d: overlay.is_displayed())
                self.wait(5).until(lambda d: self.active_matches(close_sel))

                # Focus that lands behind the overlay is pulled back to Close.
                self.driver.execute_script(
                    "document.querySelector('.nav-logo, a[href]').focus();"
                )
                self.wait(5).until(lambda d: self.active_matches(close_sel))

                self.driver.switch_to.active_element.send_keys(Keys.ESCAPE)
                self.wait(5).until(lambda d: not overlay.is_displayed())
                self.wait(5).until(lambda d: self.active_matches(opener_sel))
