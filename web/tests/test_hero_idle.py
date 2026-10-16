"""The hero's three looping animations pause once the hero scrolls away.

The grain, the twinkle and the 44-bulb chase run forever (WCAG-wise they
stop under reduced motion, see test_reduced_motion). For everyone else they
kept painting while the visitor read the showtimes two screens down; the
audit's trace put 8 of the home page's 12.5 main-thread seconds in style,
layout and paint. effects.js marks the hero `hero--offscreen` when it
leaves the viewport, and the bundle pauses the loops under that class.
"""

import re

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
            ".hero--offscreen .bulb:after",
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
            and s & {".hero:before", ".hero-stars", ".bulb:after"}
        )
        # effects.css already pauses .hero--pre-show .bulb for the power-on
        # sequence; only the offscreen rule is under test here.
        first_pause = min(
            i
            for i, (m, s, d) in enumerate(self.rules)
            if m == "" and PAUSED in d and ".hero--offscreen .bulb:after" in s
        )
        self.assertGreater(first_pause, last_animation)
        self.assertTrue(order)


class BulbChaseCostTests(SimpleTestCase):
    """The chase crossfades a lit pseudo-element instead of animating paint.

    bulb-chase animated box-shadow and a gradient on all 44 bulbs, so every
    frame repainted every bulb: the audit's trace put most of the hero's
    cost there, and pausing off screen (above) cannot help while the hero
    is the first thing on screen. Opacity on its own layer is composited,
    not painted. The look is the same two states, dim and lit, crossfaded.
    """

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.css = (CSS_DIR / "bundle.css").read_text()
        cls.rules = parse_rules(cls.css)

    def keyframes(self, name):
        match = re.search(r"@keyframes %s\{(.*?)\}\}" % re.escape(name), self.css)
        return match.group(1) + "}" if match else None

    def test_the_glow_keyframes_only_animate_opacity(self):
        body = self.keyframes("bulb-glow")
        self.assertIsNotNone(body, "no bulb-glow keyframes in the bundle")
        props = set(re.findall(r"([a-z-]+):", body))
        self.assertEqual(props, {"opacity"})

    def test_the_old_paint_heavy_chase_is_gone(self):
        self.assertIsNone(self.keyframes("bulb-chase"))

    def test_the_bulb_itself_no_longer_loops(self):
        for media, selectors, decls in self.rules:
            if media == "" and selectors == {".bulb"}:
                self.assertFalse(
                    [d for d in decls if d.startswith("animation:")], decls
                )

    def test_the_glow_runs_on_the_pseudo_element(self):
        found = [
            d
            for m, s, d in self.rules
            if m == "" and ".bulb:after" in s
            and any(x.startswith("animation:bulb-glow") for x in d)
        ]
        self.assertTrue(found)
