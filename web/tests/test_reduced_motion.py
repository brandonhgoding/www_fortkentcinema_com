"""The hero's animations stop for visitors who ask for reduced motion.

WCAG 2.2.2: anything that moves on its own for more than five seconds needs a
way to stop. The bulb chase, twinkle and grain loop forever.

This checks the built bundle rather than the source sheets because the bug it
guards against lived in the cascade: global.css had a reduced-motion block for
the hero, but Hero.css is bundled after it, so its non-!important
`.hero::before { animation: none }` lost to the grain loop declared later.
"""

import re
from pathlib import Path

from django.conf import settings
from django.test import SimpleTestCase

CSS_DIR = Path(settings.BASE_DIR) / "static" / "css"
REDUCED = "prefers-reduced-motion:reduce"


def parse_rules(css, media=""):
    """Flatten CSS into (media, selectors, declarations) in source order.

    Enough of a parser for our own sheets: comments stripped, @media blocks
    descended into, selectors normalised so `::before` matches the minifier's
    output.
    """
    css = re.sub(r"/\*.*?\*/", "", css, flags=re.S)
    rules, i = [], 0
    while i < len(css):
        open_ = css.find("{", i)
        if open_ == -1:
            break
        head = css[i:open_].strip()
        depth, j = 1, open_ + 1
        while depth:
            depth += {"{": 1, "}": -1}.get(css[j], 0)
            j += 1
        body = css[open_ + 1 : j - 1]
        if head.startswith("@media"):
            rules += parse_rules(body, re.sub(r"\s+", "", head[6:]))
        elif not head.startswith("@"):
            selectors = {
                re.sub(r"\s+", " ", s).strip().replace("::", ":")
                for s in head.split(",")
            }
            decls = [
                re.sub(r"\s+", "", d) for d in body.split(";") if ":" in d
            ]
            rules.append((media, selectors, decls))
        i = j
    return rules


def animation(decls):
    for d in decls:
        if d.startswith("animation:"):
            return d[len("animation:") :]
    return None


class HeroReducedMotionTests(SimpleTestCase):
    def setUp(self):
        bundle = CSS_DIR / "bundle.css"
        if not bundle.exists():
            self.skipTest("bundle.css not built — run `npm run build` in frontend/")
        self.bundle = parse_rules(bundle.read_text())

    def animated_hero_selectors(self):
        selectors = set()
        for media, sels, decls in parse_rules((CSS_DIR / "Hero.css").read_text()):
            value = animation(decls)
            if REDUCED not in media and value and not value.startswith("none"):
                selectors |= sels
        return selectors

    def test_hero_css_animates_something(self):
        """Guards the test below against passing vacuously."""
        self.assertIn(".hero:before", self.animated_hero_selectors())

    def test_every_hero_animation_is_off_under_reduced_motion(self):
        for selector in sorted(self.animated_hero_selectors()):
            with self.subTest(selector=selector):
                last_running = max(
                    n
                    for n, (media, sels, decls) in enumerate(self.bundle)
                    if selector in sels
                    and REDUCED not in media
                    and (animation(decls) or "none").split("!")[0] != "none"
                )
                stops = [
                    n
                    for n, (media, sels, decls) in enumerate(self.bundle)
                    if selector in sels
                    and REDUCED in media
                    and (animation(decls) or "").startswith("none")
                    and (n > last_running or "!important" in animation(decls))
                ]
                self.assertTrue(
                    stops,
                    f"{selector} still animates under prefers-reduced-motion",
                )
