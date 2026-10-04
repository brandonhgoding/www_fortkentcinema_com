"""Blog management in the dashboard: posts, drafts, authors and categories."""

import datetime
import json

from blog.models import BlogAuthor, BlogCategory, BlogPost
from cinema.models import Film
from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

User = get_user_model()


class BlogFixture(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.author = BlogAuthor.objects.create(first_name="Ada", last_name="Lovelace")
        cls.category = BlogCategory.objects.create(name="Reviews")
        cls.film = Film.objects.create(title="Dune", runtime_minutes=155)

    def setUp(self) -> None:
        User.objects.create_user(username="s", password="pw12345", is_staff=True)
        self.client.login(username="s", password="pw12345")

    def make_post(self, **overrides) -> BlogPost:
        fields = {
            "title": "A Review of Dune",
            "subtitle": "Sand, worms and a very long runtime",
            "author": self.author,
            "category": self.category,
            "post_date": datetime.date(2026, 9, 1),
            "content": "It was long.\n\nIt was good.",
        }
        fields.update(overrides)
        return BlogPost.objects.create(**fields)

    def payload(self, **overrides) -> dict:
        data = {
            "title": "Opening Night",
            "subtitle": "We are back for the season",
            "slug": "",
            "author": str(self.author.pk),
            "category": str(self.category.pk),
            "post_date": "2026-10-01",
            "content": "Doors at **six**.",
        }
        data.update(overrides)
        return data


class StaffOnlyTests(BlogFixture):
    def test_every_blog_url_requires_staff(self) -> None:
        self.client.logout()
        post = self.make_post()
        gets = [
            reverse("dashboard:blog"),
            reverse("dashboard:blog_post_create"),
            reverse("dashboard:blog_post_edit", args=[post.pk]),
            reverse("dashboard:blog_post_preview", args=[post.pk]),
            reverse("dashboard:blog_author_create"),
            reverse("dashboard:blog_author_edit", args=[self.author.pk]),
            reverse("dashboard:blog_category_create"),
            reverse("dashboard:blog_category_edit", args=[self.category.pk]),
        ]
        posts = [
            reverse("dashboard:blog_post_create"),
            reverse("dashboard:blog_post_edit", args=[post.pk]),
            reverse("dashboard:blog_post_delete", args=[post.pk]),
            reverse("dashboard:blog_markdown_preview"),
            reverse("dashboard:blog_author_delete", args=[self.author.pk]),
            reverse("dashboard:blog_category_delete", args=[self.category.pk]),
        ]
        for url in gets:
            with self.subTest(url=url):
                self.assertEqual(self.client.get(url).status_code, 302)
        for url in posts:
            with self.subTest(url=url):
                self.assertEqual(self.client.post(url).status_code, 302)
        self.assertTrue(BlogPost.objects.filter(pk=post.pk).exists())

    def test_non_staff_get_403(self) -> None:
        User.objects.create_user(username="member", password="pw12345")
        self.client.login(username="member", password="pw12345")
        self.assertEqual(self.client.get(reverse("dashboard:blog")).status_code, 403)


class NavTests(BlogFixture):
    def test_sidebar_links_to_blog(self) -> None:
        html = self.client.get(reverse("dashboard:home")).content.decode()
        self.assertIn(">Blog<", html)
        self.assertIn(f'href="{reverse("dashboard:blog")}"', html)

    def test_blog_is_gone_from_admin(self) -> None:
        User.objects.create_superuser(username="root", password="pw12345")
        self.client.login(username="root", password="pw12345")
        self.assertEqual(self.client.get("/admin/blog/blogpost/").status_code, 404)
        # FilmAdmin used to autocomplete against BlogPostAdmin.
        film_admin = self.client.get(f"/admin/cinema/film/{self.film.pk}/change/")
        self.assertEqual(film_admin.status_code, 200)


class PostListTests(BlogFixture):
    def test_lists_drafts_and_published_with_counts(self) -> None:
        self.make_post(title="Live One", subtitle="live-one")
        self.make_post(title="Draft One", subtitle="draft-one", status=BlogPost.Status.DRAFT)
        html = self.client.get(reverse("dashboard:blog")).content.decode()
        self.assertIn("Live One", html)
        self.assertIn("Draft One", html)
        self.assertIn("1 published · 1 draft", html)

    def test_drafts_sort_first(self) -> None:
        self.make_post(title="Newer Live", subtitle="newer", post_date=datetime.date(2026, 9, 9))
        self.make_post(
            title="Older Draft", subtitle="older",
            post_date=datetime.date(2026, 1, 1), status=BlogPost.Status.DRAFT,
        )
        posts = list(self.client.get(reverse("dashboard:blog")).context["posts"])
        self.assertEqual([p.title for p in posts], ["Older Draft", "Newer Live"])

    def test_filters(self) -> None:
        news = BlogCategory.objects.create(name="News")
        self.make_post(title="Dune Review", subtitle="dune")
        self.make_post(title="Hours Change", subtitle="hours", category=news)
        self.make_post(title="Dune Draft", subtitle="dune-2", status=BlogPost.Status.DRAFT)

        def titles(**params):
            resp = self.client.get(reverse("dashboard:blog"), params)
            return sorted(p.title for p in resp.context["posts"])

        self.assertEqual(titles(q="dune"), ["Dune Draft", "Dune Review"])
        self.assertEqual(titles(status="draft"), ["Dune Draft"])
        self.assertEqual(titles(category="news"), ["Hours Change"])

    def test_delete_from_list_swaps_table_and_keeps_filters(self) -> None:
        keep = self.make_post(title="Keep Me", subtitle="keep")
        gone = self.make_post(title="Delete Me", subtitle="gone")
        resp = self.client.post(
            reverse("dashboard:blog_post_delete", args=[gone.pk]),
            {"q": "keep"},
            HTTP_HX_REQUEST="true",
            HTTP_HX_TARGET="post-list",
        )
        self.assertEqual(resp.status_code, 200)
        self.assertFalse(BlogPost.objects.filter(pk=gone.pk).exists())
        html = resp.content.decode()
        self.assertIn('id="post-list"', html)
        self.assertIn(keep.title, html)
        trigger = json.loads(resp["HX-Trigger"])
        self.assertEqual(trigger["dashboard-toast"]["kind"], "success")


class CreatePostTests(BlogFixture):
    def test_new_post_form_defaults(self) -> None:
        resp = self.client.get(reverse("dashboard:blog_post_create"))
        self.assertEqual(resp.status_code, 200)
        form = resp.context["form"]
        self.assertTrue(form.instance._state.adding)
        self.assertIn('name="status" value="published"', resp.content.decode())

    def test_save_draft(self) -> None:
        resp = self.client.post(
            reverse("dashboard:blog_post_create"), self.payload(status="draft")
        )
        post = BlogPost.objects.get()
        self.assertRedirects(resp, reverse("dashboard:blog_post_edit", args=[post.pk]))
        self.assertEqual(post.status, BlogPost.Status.DRAFT)
        self.assertEqual(post.slug, "we-are-back-for-the-season")

    def test_submit_without_a_button_saves_a_draft(self) -> None:
        """Enter in a text field submits with no status. A new post must not go
        live by accident."""
        self.client.post(reverse("dashboard:blog_post_create"), self.payload())
        self.assertEqual(BlogPost.objects.get().status, BlogPost.Status.DRAFT)

    def test_publish(self) -> None:
        self.client.post(
            reverse("dashboard:blog_post_create"), self.payload(status="published")
        )
        post = BlogPost.objects.get()
        self.assertTrue(post.is_published)
        self.assertEqual(
            self.client.get(reverse("blog_detail", args=[post.slug])).status_code, 200
        )

    def test_draft_may_have_an_empty_body_but_publishing_needs_one(self) -> None:
        self.client.post(
            reverse("dashboard:blog_post_create"), self.payload(status="draft", content="")
        )
        self.assertEqual(BlogPost.objects.count(), 1)

        resp = self.client.post(
            reverse("dashboard:blog_post_create"),
            self.payload(status="published", content="", subtitle="another"),
        )
        self.assertEqual(resp.status_code, 200)
        self.assertIn("content", resp.context["form"].errors)
        self.assertEqual(BlogPost.objects.count(), 1)

    def test_custom_slug_is_slugified(self) -> None:
        self.client.post(
            reverse("dashboard:blog_post_create"), self.payload(slug="Opening Night!")
        )
        self.assertEqual(BlogPost.objects.get().slug, "opening-night")

    def test_slug_clash_is_a_field_error_not_a_crash(self) -> None:
        self.make_post(subtitle="We are back for the season")
        resp = self.client.post(reverse("dashboard:blog_post_create"), self.payload())
        self.assertEqual(resp.status_code, 200)
        self.assertIn("slug", resp.context["form"].errors)

    def test_long_subtitle_slug_fits_the_column(self) -> None:
        self.client.post(
            reverse("dashboard:blog_post_create"), self.payload(subtitle="word " * 39)
        )
        slug = BlogPost.objects.get().slug
        self.assertLessEqual(len(slug), 100)
        self.assertFalse(slug.endswith("-"))

    def test_unsluggable_subtitle_gets_a_fallback_slug(self) -> None:
        """An all-emoji or Cyrillic subtitle slugified to '', which then broke
        every reverse('blog_detail') on the site."""
        self.make_post(subtitle="Кино")  # already holds "post"
        self.client.post(
            reverse("dashboard:blog_post_create"),
            self.payload(subtitle="★★★★☆", status="published"),
        )
        post = BlogPost.objects.get(subtitle="★★★★☆")
        self.assertEqual(post.slug, "post-2")
        self.assertEqual(self.client.get(reverse("dashboard:blog")).status_code, 200)

    def test_links_films_to_the_review(self) -> None:
        other = Film.objects.create(title="Dune: Part One (re-release)")
        self.client.post(
            reverse("dashboard:blog_post_create"),
            {**self.payload(), "films": [self.film.pk, other.pk]},
        )
        post = BlogPost.objects.get()
        self.assertEqual(set(post.films.all()), {self.film, other})


class EditPostTests(BlogFixture):
    def test_edit_form_prefills_films(self) -> None:
        post = self.make_post()
        self.film.review = post
        self.film.save(update_fields=["review"])
        resp = self.client.get(reverse("dashboard:blog_post_edit", args=[post.pk]))
        self.assertEqual(resp.context["initial_films"][0]["title"], "Dune")

    def test_save_changes_keeps_a_published_post_live(self) -> None:
        post = self.make_post()
        self.client.post(
            reverse("dashboard:blog_post_edit", args=[post.pk]),
            self.payload(title="Retitled", slug=post.slug),
        )
        post.refresh_from_db()
        self.assertEqual(post.title, "Retitled")
        self.assertTrue(post.is_published)

    def test_blank_slug_on_edit_refills_from_subtitle(self) -> None:
        post = self.make_post(status=BlogPost.Status.DRAFT)
        self.client.post(
            reverse("dashboard:blog_post_edit", args=[post.pk]),
            self.payload(subtitle="Fresh angle"),
        )
        post.refresh_from_db()
        self.assertEqual(post.slug, "fresh-angle")

    def test_unpublish(self) -> None:
        post = self.make_post()
        self.client.post(
            reverse("dashboard:blog_post_edit", args=[post.pk]),
            self.payload(status="draft", slug=post.slug),
        )
        post.refresh_from_db()
        self.assertFalse(post.is_published)

    def test_unlinking_a_film_clears_its_review(self) -> None:
        post = self.make_post()
        self.film.review = post
        self.film.save(update_fields=["review"])
        self.client.post(
            reverse("dashboard:blog_post_edit", args=[post.pk]),
            self.payload(slug=post.slug),
        )
        self.film.refresh_from_db()
        self.assertIsNone(self.film.review)

    def test_save_shows_a_toast_after_redirect(self) -> None:
        post = self.make_post(status=BlogPost.Status.DRAFT)
        resp = self.client.post(
            reverse("dashboard:blog_post_edit", args=[post.pk]),
            self.payload(status="published"),
            follow=True,
        )
        self.assertContains(resp, 'id="flash-messages"')
        self.assertContains(resp, ">Published<")

    def test_delete_from_editor_redirects_to_list(self) -> None:
        post = self.make_post()
        resp = self.client.post(
            reverse("dashboard:blog_post_delete", args=[post.pk]), HTTP_HX_REQUEST="true"
        )
        self.assertEqual(resp["HX-Redirect"], reverse("dashboard:blog"))
        self.assertFalse(BlogPost.objects.filter(pk=post.pk).exists())


class PublishDateTests(BlogFixture):
    """post_date was the day the draft was started: the editor pre-fills
    today, and publishing only changed the status. A post drafted on the 1st
    and published on the 20th went out dated the 1st, sorted below newer
    posts.

    Publishing now moves the date to the publish day, but only when it is
    still the day the draft was started. A date staff set on purpose stays.
    """

    STARTED = datetime.date(2026, 9, 1)

    def make_draft(self, post_date) -> BlogPost:
        post = self.make_post(status=BlogPost.Status.DRAFT, post_date=post_date)
        started = timezone.make_aware(datetime.datetime(2026, 9, 1, 10, 0))
        BlogPost.objects.filter(pk=post.pk).update(created_at=started)
        return post

    def publish(self, post, **overrides) -> BlogPost:
        data = self.payload(
            slug=post.slug, status="published", post_date=post.post_date.isoformat()
        )
        data.update(overrides)
        self.client.post(reverse("dashboard:blog_post_edit", args=[post.pk]), data)
        post.refresh_from_db()
        return post

    def test_publishing_moves_an_untouched_date_to_the_publish_day(self) -> None:
        post = self.publish(self.make_draft(self.STARTED))
        self.assertTrue(post.is_published)
        self.assertEqual(post.post_date, timezone.localdate())

    def test_publishing_keeps_a_backdated_post(self) -> None:
        post = self.publish(self.make_draft(datetime.date(2026, 8, 15)))
        self.assertEqual(post.post_date, datetime.date(2026, 8, 15))

    def test_a_date_set_while_publishing_is_kept(self) -> None:
        """Changing the field in the same submit counts as deliberate, even
        when the new value is the start day."""
        post = self.make_draft(datetime.date(2026, 8, 15))
        post = self.publish(post, post_date=self.STARTED.isoformat())
        self.assertEqual(post.post_date, self.STARTED)

    def test_saving_a_published_post_keeps_its_date(self) -> None:
        post = self.make_draft(self.STARTED)
        BlogPost.objects.filter(pk=post.pk).update(status=BlogPost.Status.PUBLISHED)
        post.refresh_from_db()
        post = self.publish(post)
        self.assertEqual(post.post_date, self.STARTED)

    def test_saving_a_draft_keeps_its_date(self) -> None:
        post = self.publish(self.make_draft(self.STARTED), status="draft")
        self.assertEqual(post.post_date, self.STARTED)

    def test_new_posts_record_when_they_were_started(self) -> None:
        self.client.post(reverse("dashboard:blog_post_create"), self.payload(status="draft"))
        self.assertEqual(
            timezone.localdate(BlogPost.objects.get().created_at), timezone.localdate()
        )


class BodyFormatTests(BlogFixture):
    """Posts from before the editor are plain text. Editing one must not turn
    it into Markdown behind the author's back."""

    def plain_post(self) -> BlogPost:
        return self.make_post(
            content="# of times: three.\n\nMy <favorite snack>.",
            body_format=BlogPost.BodyFormat.PLAIN,
        )

    def test_editing_a_plain_post_keeps_it_plain(self) -> None:
        post = self.plain_post()
        self.client.post(
            reverse("dashboard:blog_post_edit", args=[post.pk]),
            self.payload(slug=post.slug, content="# still plain"),
        )
        post.refresh_from_db()
        self.assertEqual(post.content, "# still plain")
        self.assertEqual(post.body_format, BlogPost.BodyFormat.PLAIN)

    def test_a_plain_post_can_be_switched_to_markdown(self) -> None:
        post = self.plain_post()
        self.client.post(
            reverse("dashboard:blog_post_edit", args=[post.pk]),
            self.payload(slug=post.slug, use_markdown="on"),
        )
        post.refresh_from_db()
        self.assertEqual(post.body_format, BlogPost.BodyFormat.MARKDOWN)

    def test_editor_marks_a_plain_post_and_previews_it_as_plain(self) -> None:
        resp = self.client.get(reverse("dashboard:blog_post_edit", args=[self.plain_post().pk]))
        self.assertContains(resp, "Plain text (legacy)")
        self.assertContains(resp, 'name="use_markdown"')
        self.assertEqual(
            resp.context["preview_html"],
            "<p># of times: three.</p><p>My &lt;favorite snack&gt;.</p>",
        )

    def test_editor_has_no_legacy_note_for_markdown_posts(self) -> None:
        resp = self.client.get(reverse("dashboard:blog_post_edit", args=[self.make_post().pk]))
        self.assertNotContains(resp, "Plain text (legacy)")
        resp = self.client.get(reverse("dashboard:blog_post_create"))
        self.assertNotContains(resp, "Plain text (legacy)")

    def test_live_preview_follows_the_format(self) -> None:
        url = reverse("dashboard:blog_markdown_preview")
        plain = self.client.post(url, {"content": "# hi", "body_format": "plain"})
        self.assertEqual(plain.content.decode(), "<p># hi</p>")
        switched = self.client.post(
            url, {"content": "# hi", "body_format": "plain", "use_markdown": "on"}
        )
        self.assertEqual(switched.content.decode(), "<h2>hi</h2>")
        self.assertEqual(self.client.post(url, {"content": "# hi"}).content.decode(), "<h2>hi</h2>")


class PreviewTests(BlogFixture):
    def test_draft_preview_renders_the_public_template_noindexed(self) -> None:
        post = self.make_post(status=BlogPost.Status.DRAFT, content="# Verdict\n\n**Yes.**")
        resp = self.client.get(reverse("dashboard:blog_post_preview", args=[post.pk]))
        self.assertEqual(resp.status_code, 200)
        self.assertTemplateUsed(resp, "blog/post_detail.html")
        self.assertEqual(resp["X-Robots-Tag"], "noindex, nofollow")
        html = resp.content.decode()
        self.assertIn('content="noindex, nofollow"', html)
        self.assertIn("Draft preview", html)
        self.assertIn("<h2>Verdict</h2>", html)
        self.assertIn("<strong>Yes.</strong>", html)

    def test_markdown_preview_endpoint(self) -> None:
        resp = self.client.post(
            reverse("dashboard:blog_markdown_preview"),
            {"content": "*hi*\n\n<script>x</script>"},
        )
        self.assertEqual(resp.content.decode().strip(), "<p><em>hi</em></p>")


class AuthorCategoryTests(BlogFixture):
    def test_create_author_swaps_both_tables(self) -> None:
        resp = self.client.post(
            reverse("dashboard:blog_author_create"),
            {"first_name": "Grace", "last_name": "Hopper"},
        )
        self.assertTrue(BlogAuthor.objects.filter(slug="grace-hopper").exists())
        html = resp.content.decode()
        self.assertIn('id="author-list" hx-swap-oob="true"', html)
        self.assertIn('id="category-list" hx-swap-oob="true"', html)
        self.assertTrue(json.loads(resp["HX-Trigger"])["close-drawer"])

    def test_duplicate_author_name_is_a_form_error(self) -> None:
        resp = self.client.post(
            reverse("dashboard:blog_author_create"),
            {"first_name": "Ada", "last_name": "Lovelace"},
        )
        self.assertContains(resp, "already an author with that name")
        self.assertEqual(BlogAuthor.objects.count(), 1)

    def test_rename_category_keeps_slug(self) -> None:
        self.client.post(
            reverse("dashboard:blog_category_edit", args=[self.category.pk]),
            {"name": "Film Reviews"},
        )
        self.category.refresh_from_db()
        self.assertEqual(self.category.name, "Film Reviews")
        self.assertEqual(self.category.slug, "reviews")

    def test_duplicate_category_name_is_a_form_error(self) -> None:
        resp = self.client.post(reverse("dashboard:blog_category_create"), {"name": "Reviews"})
        self.assertContains(resp, "already a category with that name")

    def test_cannot_delete_an_author_or_category_with_posts(self) -> None:
        """These were CASCADE. Deleting an author used to delete their posts."""
        post = self.make_post()
        for url in (
            reverse("dashboard:blog_author_delete", args=[self.author.pk]),
            reverse("dashboard:blog_category_delete", args=[self.category.pk]),
        ):
            with self.subTest(url=url):
                resp = self.client.post(url)
                self.assertEqual(json.loads(resp["HX-Trigger"])["dashboard-toast"]["kind"], "error")
        self.assertTrue(BlogPost.objects.filter(pk=post.pk).exists())
        self.assertTrue(BlogAuthor.objects.filter(pk=self.author.pk).exists())

    def test_delete_unused_category(self) -> None:
        empty = BlogCategory.objects.create(name="Empty")
        self.client.post(reverse("dashboard:blog_category_delete", args=[empty.pk]))
        self.assertFalse(BlogCategory.objects.filter(pk=empty.pk).exists())
