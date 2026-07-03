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
    @mock.patch("web.views.get_now_showing", return_value=[])
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


class BlogInfiniteScrollE2E(SeleniumTestCase):
    """Blog listing's HTMX `hx-trigger="revealed"` infinite scroll. Seeds
    more posts than the first page (6) so scrolling to the bottom must
    reveal the "load more" sentinel and pull in another page.
    """

    def setUp(self):
        # NOTE: setUpTestData is a django.test.TestCase-only mechanism; this
        # base class is a LiveServerTestCase (-> TransactionTestCase), which
        # never calls it. Seed per-test in setUp instead.
        super().setUp()
        author = BlogAuthor.objects.create(first_name="Jane", last_name="Doe")
        category = BlogCategory.objects.create(name="News")
        for i in range(9):
            BlogPost.objects.create(
                title=f"Post {i}",
                subtitle=f"Subtitle {i}",
                author=author,
                category=category,
                content=f"Body content for post {i}.",
                post_date=f"2026-01-{i + 1:02d}",
            )

    def test_scrolling_to_bottom_loads_more_posts(self):
        from selenium.webdriver.common.by import By

        self.driver.get(self.live_server_url + "/blog/")

        cards = self.wait().until(
            lambda d: d.find_elements(By.CSS_SELECTOR, ".blog-card") or False
        )
        initial_count = len(cards)
        self.assertEqual(initial_count, 6)  # PostListView.paginate_by

        self.driver.execute_script(
            "window.scrollTo(0, document.body.scrollHeight);"
        )

        self.wait(15).until(
            lambda d: len(d.find_elements(By.CSS_SELECTOR, ".blog-card"))
            > initial_count
        )
        self.assertEqual(
            len(self.driver.find_elements(By.CSS_SELECTOR, ".blog-card")), 9
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
    @mock.patch("web.views.get_now_showing", return_value=[])
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
