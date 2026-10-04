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


class LeadTextBypassTests(BodyFormatFixture):
    """lead_text is set in save(). Writes that skip save() (queryset update,
    bulk_update, bulk_create) used to leave it stale or empty."""

    def lead(self, post) -> str:
        return BlogPost.objects.values_list("lead_text", flat=True).get(pk=post.pk)

    def test_queryset_update_of_content(self):
        post = self.make_post("Old opening.")
        BlogPost.objects.filter(pk=post.pk).update(content="New opening.\n\nMore.")
        self.assertEqual(self.lead(post), "New opening.")

    def test_update_filtered_on_the_field_it_changes(self):
        """The rows are picked before the update, so a filter the new value
        no longer matches still finds them."""
        post = self.make_post("Old opening.")
        BlogPost.objects.filter(content="Old opening.").update(content="New opening.")
        self.assertEqual(self.lead(post), "New opening.")

    def test_update_of_body_format_uses_each_rows_content(self):
        a = self.make_post("# A\n\nBody A.", body_format=BlogPost.BodyFormat.PLAIN)
        b = self.make_post("# B\n\nBody B.", body_format=BlogPost.BodyFormat.PLAIN)
        BlogPost.objects.filter(pk__in=[a.pk, b.pk]).update(
            body_format=BlogPost.BodyFormat.MARKDOWN
        )
        self.assertEqual(self.lead(a), "Body A.")
        self.assertEqual(self.lead(b), "Body B.")

    def test_update_with_an_expression(self):
        from django.db.models import F, Value
        from django.db.models.functions import Concat

        post = self.make_post("Old opening.")
        BlogPost.objects.filter(pk=post.pk).update(
            content=Concat(Value("Prefix.\n\n"), F("content"))
        )
        self.assertEqual(self.lead(post), "Prefix.")

    def test_related_manager_update(self):
        post = self.make_post("Old opening.")
        self.author.blogpost_set.update(content="Via the author.")
        self.assertEqual(self.lead(post), "Via the author.")

    def test_update_returns_the_row_count(self):
        self.make_post("One.")
        self.make_post("Two.")
        self.assertEqual(BlogPost.objects.update(content="Same."), 2)

    def test_unrelated_update_costs_one_query(self):
        post = self.make_post("Opening.")
        with self.assertNumQueries(1):
            BlogPost.objects.filter(pk=post.pk).update(title="Retitled")

    def test_content_update_costs_a_fixed_number_of_queries(self):
        for n in range(5):
            self.make_post(f"Opening {n}.")
        # Select the rows, update, read them back, write lead_text.
        with self.assertNumQueries(4):
            BlogPost.objects.update(content="Same.")

    def test_bulk_update(self):
        a, b = self.make_post("Old A."), self.make_post("Old B.")
        a.content, b.content = "New A.", "New B."
        with self.assertNumQueries(1):
            BlogPost.objects.bulk_update([a, b], ["content"])
        self.assertEqual(self.lead(a), "New A.")
        self.assertEqual(self.lead(b), "New B.")
        self.assertEqual(a.lead_text, "New A.")

    def test_bulk_update_of_body_format(self):
        post = self.make_post("# H\n\nBody.", body_format=BlogPost.BodyFormat.PLAIN)
        post.body_format = BlogPost.BodyFormat.MARKDOWN
        BlogPost.objects.bulk_update([post], ["body_format"])
        self.assertEqual(self.lead(post), "Body.")

    def test_bulk_create(self):
        (post,) = BlogPost.objects.bulk_create([
            BlogPost(
                title="T", subtitle="Bulk", slug="bulk", author=self.author,
                category=self.category, post_date=datetime.date(2024, 1, 1),
                content="Bulk opening.\n\nMore.",
            )
        ])
        self.assertEqual(self.lead(post), "Bulk opening.")

    def test_save_with_lead_text_deferred_does_not_fetch_it(self):
        post = self.make_post("Opening.")
        post = BlogPost.objects.defer("lead_text").get(pk=post.pk)
        post.content = "Changed."
        with self.assertNumQueries(1):
            post.save(update_fields=["content"])
        self.assertEqual(self.lead(post), "Changed.")
