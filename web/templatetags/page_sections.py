"""Page-section composition: dividers that only appear between live content.

The home page is a stack of sections with an ornament divider between each
one. Emitting those dividers unconditionally is wrong the moment a section
can disappear, and two of them can: cta_sponsored.html and cta_vote.html
render nothing at all between a sponsored run and between vote rounds. The
workaround those two carry today — a trailing divider tucked inside their own
``{% if %}`` — fixes their own case and nothing else, and it cannot fix the
first or last slot in the stack at all.

``{% section %}`` inverts the rule: the divider is not emitted by the page, it
is emitted by whichever section turns out to have a live section in front of
it. A section that renders to whitespace contributes nothing and is skipped,
so the page can never open with a divider, end with one, or stack two.

    {% load page_sections %}
    {% section %}{% include "partials/hero.html" %}{% endsection %}
    {% section %}{% include "partials/cta_vote.html" %}{% endsection %}

A section whose own markup ends with an ornament divider has that divider
absorbed: the tag owns the seam, so the partial's trailing copy would be a
duplicate here. This is deliberate — it lets cta_sponsored.html and
cta_vote.html keep their internal workaround (they are rendered on their own
elsewhere, and neither is ours to edit) without double-spacing this page.
"""

from django import template
from django.template.loader import render_to_string
from django.utils.safestring import mark_safe

register = template.Library()

DIVIDER_TEMPLATE = "partials/ornament_divider.html"

# Keys on the render context, which is per-render and per-template, so two
# requests (or an {% include %}d sub-template) can never see each other's state.
_EMITTED = "web.page_sections.emitted"
_DIVIDER = "web.page_sections.divider"


def _divider(context):
    markup = context.render_context.get(_DIVIDER)
    if markup is None:
        markup = render_to_string(DIVIDER_TEMPLATE).strip()
        context.render_context[_DIVIDER] = markup
    return markup


class SectionNode(template.Node):
    def __init__(self, nodelist):
        self.nodelist = nodelist

    def render(self, context):
        body = self.nodelist.render(context).strip()
        divider = _divider(context)

        # Absorb a trailing divider the section emitted for itself.
        while body.endswith(divider):
            body = body[: -len(divider)].rstrip()

        if not body:
            return ""

        if context.render_context.get(_EMITTED):
            return mark_safe(f"{divider}\n{body}\n")

        context.render_context[_EMITTED] = True
        return mark_safe(f"{body}\n")


@register.tag("section")
def do_section(parser, token):
    bits = token.split_contents()
    if len(bits) != 1:
        raise template.TemplateSyntaxError("%r takes no arguments" % bits[0])
    nodelist = parser.parse(("endsection",))
    parser.delete_first_token()
    return SectionNode(nodelist)
