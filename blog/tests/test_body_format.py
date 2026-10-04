"""Plain-text and Markdown post bodies.

Posts were plain text, split on blank lines and autoescaped, until the
dashboard editor arrived with Markdown. Parsing the old posts as Markdown
changed them: a line opening with '#' became a heading, "1986." started a
numbered list, and "<favorite snack>" vanished as an HTML tag. Every post
that existed then is marked plain and renders exactly as it used to.
"""

import datetime
from importlib import import_module
from unittest import mock

from django.apps import apps
from django.test import TestCase
from django.utils.html import escape

from blog import rendering
from blog.models import BlogAuthor, BlogCategory, BlogPost

LEGACY_BODY = (
    "# of times I've seen it: three.\n\n"
    "1986. The year it came out.\n\n"
    "My <favorite snack> & a soda\nwith a line break."
)
# What the old `{% for para in post.content|paragraphs %}<p>{{ para }}</p>{% endfor %}`
# loop printed for LEGACY_BODY.
LEGACY_HTML = (
    "<p># of times I&#x27;ve seen it: three.</p>"
    "<p>1986. The year it came out.</p>"
    "<p>My &lt;favorite snack&gt; &amp; a soda\nwith a line break.</p>"
)


class BodyFormatFixture(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.author = BlogAuthor.objects.create(first_name="Ada", last_name="Lovelace")
        cls.category = BlogCategory.objects.create(name="Reviews")

    def make_post(self, content, **extra) -> BlogPost:
        fields = {
            "title": "A Post",
            "subtitle": f"post {BlogPost.objects.count()}",
            "author": self.author,
            "category": self.category,
            "post_date": datetime.date(2024, 1, 1),
            "content": content,
        }
        fields.update(extra)
        return BlogPost.objects.create(**fields)


class PlainBodyTests(BodyFormatFixture):
    def test_new_posts_default_to_markdown(self):
        self.assertEqual(self.make_post("x").body_format, BlogPost.BodyFormat.MARKDOWN)

    def test_plain_post_renders_exactly_as_before_markdown(self):
        post = self.make_post(LEGACY_BODY, body_format=BlogPost.BodyFormat.PLAIN)
        html = self.client.get(post.get_absolute_url()).content.decode()
        self.assertIn(f'<div class="blog-detail-body">\n        {LEGACY_HTML}\n      </div>', html)

    def test_markdown_post_still_renders_markdown(self):
        post = self.make_post("# Verdict\n\n**Go.**")
        html = self.client.get(post.get_absolute_url()).content.decode()
        self.assertIn("<h2>Verdict</h2>", html)
        self.assertIn("<strong>Go.</strong>", html)

    def test_plain_card_excerpt_is_the_old_first_paragraph(self):
        """The old excerpt: the first blank-line paragraph, as typed."""
        self.make_post(LEGACY_BODY, body_format=BlogPost.BodyFormat.PLAIN)
        html = self.client.get("/blog/").content.decode()
        self.assertIn(
            '<p class="blog-card-excerpt"># of times I&#x27;ve seen it: three.</p>', html
        )

    def test_markdown_card_excerpt_strips_the_syntax(self):
        self.make_post("# Verdict\n\nA **bold** take.")
        html = self.client.get("/blog/").content.decode()
        self.assertIn('<p class="blog-card-excerpt">A bold take.</p>', html)


EXCERPT_BODIES = [
    (BlogPost.BodyFormat.MARKDOWN, "# Verdict\n\nA **bold** take on [Dune](https://x.test)."),
    (BlogPost.BodyFormat.MARKDOWN, "![poster](/a.png)\n\n" + "word " * 60),
    (BlogPost.BodyFormat.MARKDOWN, ""),
    (BlogPost.BodyFormat.PLAIN, LEGACY_BODY),
    (BlogPost.BodyFormat.PLAIN, "x" * 200 + "\n\nSecond."),
]


class StoredExcerptTests(BodyFormatFixture):
    """Cards used to render each post's whole Markdown body, on every request,
    to cut a 150-character excerpt from it. The first paragraph is now
    worked out when the post is saved."""

    def test_listing_does_not_render_bodies(self):
        for body_format, body in EXCERPT_BODIES:
            self.make_post(body, body_format=body_format)
        with mock.patch.object(
            rendering, "render_markdown", wraps=rendering.render_markdown
        ) as render:
            self.client.get("/blog/")
        render.assert_not_called()

    def test_card_excerpt_is_unchanged(self):
        """The stored text, truncated, is what rendering the body gave."""
        for body_format, body in EXCERPT_BODIES:
            with self.subTest(body=body[:30]):
                post = self.make_post(body, body_format=body_format)
                expected = rendering.truncate_excerpt(
                    rendering.first_paragraph(body, body_format), 150
                )
                html = self.client.get("/blog/").content.decode()
                self.assertIn(f'<p class="blog-card-excerpt">{escape(expected)}</p>', html)
                post.delete()

    def test_editing_the_body_updates_the_excerpt(self):
        post = self.make_post("Old opening.")
        post.content = "New opening."
        post.save(update_fields=["content"])
        post.refresh_from_db()
        self.assertEqual(post.lead_text, "New opening.")

    def test_switching_format_updates_the_excerpt(self):
        post = self.make_post("# Heading\n\nBody.", body_format=BlogPost.BodyFormat.PLAIN)
        self.assertEqual(post.lead_text, "# Heading")
        post.body_format = BlogPost.BodyFormat.MARKDOWN
        post.save()
        post.refresh_from_db()
        self.assertEqual(post.lead_text, "Body.")

    def test_backfill_migration_fills_existing_posts(self):
        post = self.make_post("# Heading\n\nBody.", body_format=BlogPost.BodyFormat.PLAIN)
        BlogPost.objects.filter(pk=post.pk).update(lead_text="")
        migration = import_module("blog.migrations.0022_blogpost_lead_text")
        migration.backfill_lead_text(apps, None)
        post.refresh_from_db()
        self.assertEqual(post.lead_text, "# Heading")


class MarkExistingPostsPlainMigrationTests(BodyFormatFixture):
    """Runs the data migration's function on real rows. Every other test
    creates its posts after the migrations have run."""

    def test_every_existing_post_becomes_plain(self):
        a = self.make_post(LEGACY_BODY)
        b = self.make_post("Second.", status=BlogPost.Status.DRAFT)
        migration = import_module("blog.migrations.0021_blogpost_body_format")
        migration.mark_existing_posts_plain(apps, None)
        for post in (a, b):
            post.refresh_from_db()
            self.assertEqual(post.body_format, BlogPost.BodyFormat.PLAIN)
