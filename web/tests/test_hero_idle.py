"""The hero's looping animations pause once the hero scrolls away.

The grain and the twinkle run forever (WCAG-wise they
stop under reduced motion, see test_reduced_motion). For everyone else they
kept painting while the visitor read the showtimes two screens down; the
audit's trace put 8 of the home page's 12.5 main-thread seconds in style,
layout and paint. effects.js marks the hero `hero--offscreen` when it
leaves the viewport, and the bundle pauses the loops under that class.
"""

from django.test import SimpleTestCase

from web.tests.test_reduced_motion import CSS_DIR, parse_rules

PAUSED = "animation-play-state:paused"


class HeroIdleCssTests(SimpleTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.rules = parse_rules((CSS_DIR / "bundle.css").read_text())

    def paused_selectors(self):
        found = set()
        for media, selectors, decls in self.rules:
            if media == "" and PAUSED in decls:
                found |= selectors
        return found

    def test_bundle_pauses_each_loop_under_the_offscreen_class(self):
        paused = self.paused_selectors()
        for selector in (
            ".hero--offscreen:before",
            ".hero--offscreen .hero-stars",
        ):
            with self.subTest(selector=selector):
                self.assertIn(selector, paused)

    def test_offscreen_rule_comes_after_the_animations_it_pauses(self):
        # Same specificity tier as the loops' own rules, so source order is
        # what makes the pause win. The reduced-motion test exists because
        # this exact kind of ordering bug already shipped once.
        order = [i for i, (m, s, d) in enumerate(self.rules) if m == ""]
        last_animation = max(
            i
            for i, (m, s, d) in enumerate(self.rules)
            if m == "" and any(x.startswith("animation:") for x in d)
            and s & {".hero:before", ".hero-stars"}
        )
        first_pause = min(
            i
            for i, (m, s, d) in enumerate(self.rules)
            if m == "" and PAUSED in d and ".hero--offscreen .hero-stars" in s
        )
        self.assertGreater(first_pause, last_animation)
        self.assertTrue(order)


class MarqueeGoneTests(SimpleTestCase):
    """The bulb marquee was removed 2026-10-31; none of its CSS ships."""

    def test_no_bulb_or_marquee_rules_in_the_bundle(self):
        css = (CSS_DIR / "bundle.css").read_text()
        for gone in (".bulb", ".marquee-", "@keyframes bulb-", "hero--pre-show",
                     "curtain-reveal"):
            with self.subTest(gone=gone):
                self.assertNotIn(gone, css)
