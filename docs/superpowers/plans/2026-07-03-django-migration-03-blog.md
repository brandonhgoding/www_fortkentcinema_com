# Django Migration — Plan 3: Blog + Site Chrome Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship the server-rendered Blog list (`/blog`, with HTMX infinite scroll) and Blog detail (`/blog/<slug>`, with correct per-post `<meta>`/`og:` tags — the fix for the original link-preview problem), and complete the site's global chrome by porting the real Nav (with a working mobile menu) and Footer, which are still empty placeholders.

**Architecture:** The blog is native to this Django project (`blog.models.BlogPost`), so pages are plain model queries — no API, no client fetch. A `ListView` renders `/blog` (paginated) and doubles as the HTMX infinite-scroll fragment source; a `DetailView` renders `/blog/<slug>` and overrides the base template's meta/OG blocks with real post data. Nav/Footer become real partials in `base.html` (Alpine drives the mobile menu). HTMX is vendored (no runtime CDN) for the infinite scroll.

**Tech Stack:** Django 5.2.3 class-based generic views + templates, Django `Paginator`, HTMX (vendored) for infinite scroll, Alpine.js (already vendored) for the mobile menu + copy-link. Tests: Django `unittest`.

## Global Constraints

- Target repo: `api_fortkentcinema_com`, branch `feat/django-frontend-migration` (continues from Plans 1–2).
- Django 5.2.3; existing `api/` DRF surface untouched. Activate `.venv` (`source .venv/bin/activate`) for Django commands; `.env` (gitignored, `DEBUG=True`) auto-loads.
- Markup is ported to preserve **every CSS class name and DOM structure** from the source React component (pixel-identical bar). CSS is already in `static/css/` from Plan 1; global chrome sheets (Nav.css, Footer.css) are linked in `base.html`, page sheets via `{% block extra_css %}`.
- `BlogPost` fields (see `blog/models.py`): `id` (UUID), `title`, `subtitle` (the slug source), `author` (FK → `first_name`/`last_name`), `category` (FK → `name`), `post_date` (Date), `content` (Text), `summary` (nullable), `header_image` (S3 `ImageField`), `slug`. Model `Meta.ordering = ["-post_date"]`.
- Blog list pagination: **6 per page** (matches the DRF `PAGE_SIZE = 6` the SPA consumed).
- Interactivity: **HTMX** for server-driven infinite scroll (fragments), **Alpine** for the nav mobile menu + copy-link. All post data is server-rendered.
- Multi-line template comments use `{% comment %}` (single-line `{# #}` only — a multi-line `{# #}` leaks as page text). The existing `test_no_template_comment_leaks_into_page` guards home; keep new templates clean.
- Effects: the blog grids use `data-spotlight`; cards are `<a>`-wrapped, and `cardSpotlight.js`'s default selector already matches `:scope > article, :scope > a` (Plan 2 fix), so no effects change is needed.
- TDD: failing test first each task. Commit after each green task. SPA source: `/Users/bgoding/code/SoftwareMaine/www_fortkentcinema_com`.

---

### Task 1: Real Nav + Footer (global chrome)

Replaces the empty `nav.html`/`footer.html` placeholders with faithful ports. Every page renders these via `base.html`, so this makes the whole site navigable.

**Files:**
- Modify: `templates/partials/nav.html`, `templates/partials/footer.html`
- Modify: `templates/base.html` (link `Nav.css` + `Footer.css` in `<head>`)
- Create: `web/tests/test_chrome.py`
- Reference: SPA `src/components/Nav/Nav.jsx`, `src/components/Footer/Footer.jsx`

**Interfaces:**
- Consumes: `site_config` (already a context processor) for `cinema` + `navigation` + `social`.
- Produces: `partials/nav.html` (nav with `nav-container`, `nav-logo`, `nav-hamburger`, `nav-links`), `partials/footer.html` (footer brand/address/social/copyright).

- [ ] **Step 1: Write the failing test**

Create `web/tests/test_chrome.py`:

```python
from django.test import TestCase
from django.urls import reverse


class ChromeTests(TestCase):
    def test_nav_renders_logo_and_links(self):
        html = self.client.get(reverse("home")).content.decode()
        self.assertIn('class="nav-logo"', html)
        self.assertIn("FORT KENT CINEMA", html)          # logo = cinema name uppercased
        self.assertIn('class="nav-link"', html)
        self.assertIn("/blog", html)                      # a route nav item
        self.assertIn('class="nav-hamburger"', html)      # mobile toggle present

    def test_footer_renders_address_and_social(self):
        html = self.client.get(reverse("home")).content.decode()
        self.assertIn('class="footer"', html)
        self.assertIn("13 Hall Street", html)             # address from site_config
        self.assertIn("facebook.com/fortkentcinema", html)  # social link
        self.assertIn("All rights reserved", html)        # copyright line
```

- [ ] **Step 2: Run → fail**

Run: `source .venv/bin/activate && python manage.py test web.tests.test_chrome`
Expected: FAIL (placeholders have no `nav-logo`/`footer` content).

- [ ] **Step 3: Port Nav → `partials/nav.html`**

Transcribe `Nav.jsx` preserving all classes (`nav`, `nav-container`, `nav-logo`, `nav-hamburger`, `nav-hamburger-line`, `nav-links`, `nav-link`). React→server mapping:
- `cinema.name.toUpperCase()` → `{{ site_config.cinema.name|upper }}`; logo links to `/`.
- **Mobile menu via Alpine:** put `x-data="{ open: false }"` on the `<nav>`; hamburger `<button ... @click="open = !open" :aria-expanded="open" :aria-label="open ? 'Close menu' : 'Open menu'">`; the `<ul>` uses `:class="{ 'nav-links--open': open }"` (keep the base `nav-links` class); add `@keydown.escape.window="open = false"` on the nav; each link `@click="open = false"`.
- **Context-aware nav items:** loop `site_config.navigation`. For a route item (`item.href` starts with `/`): `<a href="{{ item.href }}" class="nav-link">`. For a hash item (`#...`): on the homepage keep the hash; elsewhere prefix `/`:
  ```django
  {% for item in site_config.navigation %}
    <li>
      {% if item.href|slice:":1" == "/" %}
        <a href="{{ item.href }}" class="nav-link" @click="open = false">{{ item.label }}</a>
      {% else %}
        <a href="{% if request.path == '/' %}{{ item.href }}{% else %}/{{ item.href }}{% endif %}" class="nav-link" @click="open = false">{{ item.label }}</a>
      {% endif %}
    </li>
  {% endfor %}
  ```

- [ ] **Step 4: Port Footer → `partials/footer.html`**

Transcribe `Footer.jsx` preserving classes (`footer`, `footer-container`, `footer-grid`, `footer-brand`, `footer-logo`, `footer-tagline`, `footer-address`, `footer-phone`, `footer-about-link`, `footer-bottom`, `footer-copyright`, `footer-social`, `social-link`). Mapping:
- `cinema.name.toUpperCase()` → `{{ site_config.cinema.name|upper }}`; tagline, address fields from `site_config.cinema.address`.
- Phone `tel:` href: `href="tel:{{ site_config.cinema.phone|cut:' '|cut:'('|cut:')'|cut:'-' }}"` (strip non-digits; the SPA used a regex — chained `cut` filters produce the same digits-only result for the "(207) 231-5287" format).
- `currentYear` → `{% now "Y" %}`.
- Social: only render facebook when `site_config.social.facebook` (the SPA also had instagram/twitter guards, but `site_config.social` only has facebook — render just that block; keep the exact `social-link` + facebook SVG markup from the source). The commented-out `footer-column` blocks in the source stay omitted.
- `About Us` link → `<a href="/about" class="footer-about-link">`.

- [ ] **Step 5: Link chrome CSS in base.html**

In `templates/base.html`, after the `effects.css` link (before `{% block extra_css %}`), add:

```django
    <link rel="stylesheet" href="{% static 'css/Nav.css' %}" />
    <link rel="stylesheet" href="{% static 'css/Footer.css' %}" />
```

- [ ] **Step 6: Run → pass**, then full suite.

Run: `python manage.py test web.tests.test_chrome && python manage.py test`
Expected: all green (Plan 2's 41 + the 2 new).

- [ ] **Step 7: Commit**

```bash
git add templates/partials/nav.html templates/partials/footer.html templates/base.html web/tests/test_chrome.py
git commit -m "feat(web): port real Nav (Alpine mobile menu) + Footer as global chrome"
```

---

### Task 2: Shared blog card partial + excerpt/paragraphs filters

Extracts a reusable `blog_card.html` (used by the list, and refactors the Plan 2 home teaser to use it), and adds the content-formatting template filters the SPA had (`getExcerpt`, paragraph split).

**Files:**
- Create: `templates/partials/blog_card.html`, `blog/templatetags/__init__.py`, `blog/templatetags/blog_extras.py`, `blog/tests/test_blog_extras.py`
- Modify: `templates/partials/blog_teaser.html` (include the shared card instead of inlined markup)
- Reference: SPA `src/components/BlogCard/BlogCard.jsx` (getExcerpt/formatDate + markup)

**Interfaces:**
- Produces:
  - `blog_extras.excerpt(content, max_length=150)` — first paragraph (split on blank line `\n\n`, after normalizing `\r\n`/`\r`→`\n`), truncated to `max_length` + `"..."` when longer. Empty string for falsy input.
  - `blog_extras.paragraphs(content)` — list of non-blank paragraphs (split on `\n\n`), for the detail body.
  - `partials/blog_card.html` — renders one `post` (a `BlogPost` instance): image (or 📝 placeholder), category badge, title, subtitle, excerpt, author, date, "Read More". Uses `post.header_image`, `post.category.name`, `post.title`, `post.subtitle`, `post.content`, `post.author.first_name/last_name`, `post.post_date`.

- [ ] **Step 1: Write the failing filter test**

Create `blog/templatetags/__init__.py` (empty) and `blog/tests/test_blog_extras.py`:

```python
from django.test import SimpleTestCase
from blog.templatetags.blog_extras import excerpt, paragraphs


class ExcerptTests(SimpleTestCase):
    def test_first_paragraph_short(self):
        self.assertEqual(excerpt("Hello world.\n\nSecond para."), "Hello world.")

    def test_truncates_long_first_paragraph(self):
        text = "x" * 200
        out = excerpt(text, 150)
        self.assertTrue(out.endswith("..."))
        self.assertEqual(len(out), 153)

    def test_normalizes_crlf(self):
        self.assertEqual(excerpt("A.\r\n\r\nB."), "A.")

    def test_empty(self):
        self.assertEqual(excerpt(""), "")
        self.assertEqual(excerpt(None), "")


class ParagraphsTests(SimpleTestCase):
    def test_splits_and_drops_blanks(self):
        self.assertEqual(paragraphs("A.\n\nB.\n\n\n\nC."), ["A.", "B.", "C."])

    def test_empty(self):
        self.assertEqual(paragraphs(""), [])
        self.assertEqual(paragraphs(None), [])
```

- [ ] **Step 2: Run → fail** (`No module named 'blog.templatetags.blog_extras'`).

Run: `python manage.py test blog.tests.test_blog_extras`

- [ ] **Step 3: Implement `blog/templatetags/blog_extras.py`**

```python
from django import template

register = template.Library()


def _normalize(content):
    return (content or "").replace("\r\n", "\n").replace("\r", "\n")


@register.filter
def excerpt(content, max_length=150):
    text = _normalize(content)
    if not text:
        return ""
    first = text.split("\n\n")[0]
    if len(first) <= max_length:
        return first
    return first[:max_length].strip() + "..."


@register.filter
def paragraphs(content):
    text = _normalize(content)
    if not text:
        return []
    return [p for p in text.split("\n\n") if p.strip()]
```

- [ ] **Step 4: Run → pass.**

- [ ] **Step 5: Create `partials/blog_card.html`**

Transcribe `BlogCard.jsx` markup preserving classes (`blog-card`, `blog-card-image`, `blog-card-img`, `blog-card-placeholder`, `blog-card-placeholder-icon`, `blog-card-category`, `blog-card-content`, `blog-card-title`, `blog-card-subtitle`, `blog-card-excerpt`, `blog-card-meta`, `blog-card-author`, `blog-card-date`, `blog-card-read-more`). Load the filters at top: `{% load blog_extras %}`. Mapping:
- Image: `{% if post.header_image %}<img src="{{ post.header_image.url }}" alt="{{ post.title }}" class="blog-card-img" onerror="this.style.display='none';this.nextElementSibling.style.display='flex'">{% endif %}` then the placeholder div with `style="display: {% if post.header_image %}none{% else %}flex{% endif %}"` and the 📝 icon.
- Category badge: `{% if post.category %}<span class="blog-card-category">{{ post.category.name }}</span>{% endif %}`.
- Title/subtitle; excerpt `{{ post.content|excerpt }}`; author `{% if post.author %}...{{ post.author.first_name }} {{ post.author.last_name }}{% endif %}`; date `{{ post.post_date|date:"F j, Y" }}` (matches the SPA's "Month D, Year"); "Read More" span.

- [ ] **Step 6: Refactor `blog_teaser.html` to include the shared card**

Replace the inlined blog-card markup inside `blog_teaser.html`'s post loop with `{% include "partials/blog_card.html" %}` (the loop variable must be named `post`, or pass `with post=... `). Keep the teaser's surrounding structure (section header, `blog-grid blog-grid-preview`, the `<a class="blog-card-link">` wrappers, view-all link) unchanged. This is a DRY cleanup of code this task touches.

- [ ] **Step 7: Add a card render test + confirm teaser still renders**

Add to `blog/tests/` a small `TestCase` (needs DB): create a `BlogAuthor`+`BlogCategory`+`BlogPost`, render the home page, assert the post's title + `blog-card` class appear (guards the teaser refactor). Run `python manage.py test blog web` → green.

- [ ] **Step 8: Commit**

```bash
git add templates/partials/blog_card.html templates/partials/blog_teaser.html blog/templatetags/ blog/tests/
git commit -m "feat(web): shared blog_card partial + excerpt/paragraphs filters; DRY the home teaser"
```

---

### Task 3: Blog list page (`/blog`) with HTMX infinite scroll

`PostListView` (a `ListView`) renders `/blog` paginated 6/page, and returns just the card fragment on HTMX requests. Vendors HTMX. Infinite scroll uses a `hx-trigger="revealed"` sentinel that appends the next page and a running count via an out-of-band swap.

**Files:**
- Create: `blog/site_views.py`, `blog/urls_site.py`, `blog/templates/blog/post_list.html`, `blog/templates/blog/_post_cards.html`, `blog/tests/test_site_views.py`
- Create: `static/js/htmx.min.js` (vendored)
- Modify: `fortkentcinema/urls.py` (mount `blog.urls_site` at `blog/`), `templates/base.html` (HTMX `<script>`)
- Reference: SPA `src/pages/BlogListPage.jsx`

**Interfaces:**
- Consumes: `BlogPost.objects.all()` (model ordering `-post_date`), `partials/blog_card.html`.
- Produces:
  - URL name `blog_list` at path `blog/` (`""` within `urls_site`).
  - `PostListView(ListView)`: `model=BlogPost`, `paginate_by=6`, `context_object_name="posts"`, `template_name="blog/post_list.html"`; when the request is HTMX (`HX-Request` header present), renders `blog/_post_cards.html` (the fragment) instead of the full page.
  - `_post_cards.html`: the `<a href="/blog/<slug>" class="blog-list-card-link">`-wrapped cards for the current page + either a next-page sentinel or the "You've reached the end" block + an OOB count update.

- [ ] **Step 1: Vendor HTMX + wire base.html**

```bash
cd /Users/bgoding/code/SoftwareMaine/api_fortkentcinema_com
curl -sL https://unpkg.com/htmx.org@2.0.3/dist/htmx.min.js -o static/js/htmx.min.js
test -s static/js/htmx.min.js && echo OK
```

In `templates/base.html`, add before the effects module script (end of body) or in head with defer — HTMX has no defer requirement, load it in `<head>` after Alpine:

```django
    <script defer src="{% static 'js/htmx.min.js' %}"></script>
```

- [ ] **Step 2: Write the failing test**

Create `blog/tests/test_site_views.py`:

```python
from django.test import TestCase
from django.urls import reverse
from blog.models import BlogAuthor, BlogCategory, BlogPost


class BlogListTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        author = BlogAuthor.objects.create(first_name="Ada", last_name="Lovelace")
        cat = BlogCategory.objects.create(name="News")
        for i in range(8):  # > paginate_by (6)
            BlogPost.objects.create(
                title=f"Post {i}", subtitle=f"sub-{i}", author=author, category=cat,
                post_date=f"2026-01-0{i+1}" if i < 9 else "2026-02-01",
                content=f"Body paragraph for post {i}.",
            )

    def test_list_200_and_template(self):
        resp = self.client.get(reverse("blog_list"))
        self.assertEqual(resp.status_code, 200)
        self.assertTemplateUsed(resp, "blog/post_list.html")
        self.assertTemplateUsed(resp, "base.html")

    def test_list_meta(self):
        html = self.client.get(reverse("blog_list")).content.decode()
        self.assertIn("Blog | Fort Kent Cinema", html)   # title/og:title
        self.assertIn('class="blog-list-grid"', html)

    def test_paginates_six(self):
        resp = self.client.get(reverse("blog_list"))
        self.assertEqual(len(resp.context["posts"]), 6)
        self.assertTrue(resp.context["page_obj"].has_next())

    def test_htmx_returns_fragment_only(self):
        resp = self.client.get(reverse("blog_list") + "?page=2", HTTP_HX_REQUEST="true")
        self.assertTemplateUsed(resp, "blog/_post_cards.html")
        self.assertTemplateNotUsed(resp, "base.html")     # fragment, not full page
        html = resp.content.decode()
        self.assertIn("blog-list-card-link", html)
        self.assertIn("You&#x27;ve reached the end", html)  # page 2 is last (8 posts, 6/page)
```

- [ ] **Step 3: Run → fail** (`blog_list` not found).

- [ ] **Step 4: Implement the view + urls**

Create `blog/site_views.py`:

```python
from django.views.generic import ListView
from .models import BlogPost


class PostListView(ListView):
    model = BlogPost
    paginate_by = 6
    context_object_name = "posts"
    template_name = "blog/post_list.html"

    def get_template_names(self):
        if self.request.headers.get("HX-Request"):
            return ["blog/_post_cards.html"]
        return [self.template_name]

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        # Template can't do request.headers.HX-Request (hyphen); expose a flag.
        ctx["is_htmx"] = bool(self.request.headers.get("HX-Request"))
        return ctx
```

Create `blog/urls_site.py`:

```python
from django.urls import path
from .site_views import PostListView

urlpatterns = [
    path("", PostListView.as_view(), name="blog_list"),
]
```

In `fortkentcinema/urls.py`, add BEFORE the `web.urls` catch-all include:

```python
    path("blog/", include("blog.urls_site")),
```

(Import `include` is already present.)

- [ ] **Step 5: Create the templates**

`blog/templates/blog/post_list.html`:

```django
{% extends "base.html" %}
{% load static %}

{% block title %}Blog | Fort Kent Cinema{% endblock %}
{% block description %}News, reviews, and updates from Fort Kent Cinema. Stay up to date with the latest movie announcements, events, and community news.{% endblock %}
{% block og_title %}Blog | Fort Kent Cinema{% endblock %}
{% block og_description %}News, reviews, and updates from Fort Kent Cinema.{% endblock %}

{% block extra_css %}
  <link rel="stylesheet" href="{% static 'css/BlogListPage.css' %}" />
  <link rel="stylesheet" href="{% static 'css/BlogCard.css' %}" />
{% endblock %}

{% block content %}
<div class="blog-list-page">
  <div class="blog-list-container">
    <div class="blog-list-header" data-reveal>
      <a href="/" class="blog-list-back">&larr; Back to Home</a>
      <h1 class="blog-list-title">BLOG</h1>
      <p class="blog-list-subtitle">News, reviews, and updates from Fort Kent Cinema</p>
    </div>
    <div class="blog-list-grid" data-spotlight>
      {% include "blog/_post_cards.html" %}
    </div>
    <div class="blog-list-count" aria-live="polite" role="status" id="blog-count">
      Showing {{ page_obj.end_index }} of {{ paginator.count }} posts
    </div>
  </div>
</div>
{% endblock %}
```

`blog/templates/blog/_post_cards.html` (the fragment — cards + sentinel/end + OOB count):

```django
{% load static %}
{% for post in posts %}
  <a href="/blog/{{ post.slug }}" class="blog-list-card-link">{% include "partials/blog_card.html" %}</a>
{% endfor %}
{% if page_obj.has_next %}
  <div class="blog-list-load-more"
       hx-get="{% url 'blog_list' %}?page={{ page_obj.next_page_number }}"
       hx-trigger="revealed"
       hx-swap="outerHTML"
       role="status" aria-live="polite">
    <div class="blog-list-loading-more"><p>Loading more posts...</p></div>
  </div>
{% else %}
  <div class="blog-list-end"><p>You've reached the end</p></div>
{% endif %}
{% if is_htmx %}
  <div id="blog-count" hx-swap-oob="true" class="blog-list-count" aria-live="polite" role="status">
    Showing {{ page_obj.end_index }} of {{ paginator.count }} posts
  </div>
{% endif %}
```

Notes:
- The sentinel is the last child of `.blog-list-grid`; `hx-swap="outerHTML"` replaces it with the next page's cards + the next sentinel (or the end block), so cards append inside the grid.
- On the initial full-page render the sentinel/end block is inside the grid too (from the same include) — correct.
- The OOB count block only emits on HTMX requests (guarded by the `is_htmx` context flag set in the view), updating the standalone `#blog-count` each load. `page_obj.end_index` is the 1-based index of the last item on the current page = cumulative count.
- New `<a>` cards are automatically covered by the existing card-spotlight listener (it queries `:scope > article, :scope > a` live per pointer move), so no effects re-arm is needed.

- [ ] **Step 6: Run → pass**, then full suite.

Run: `python manage.py test blog.tests.test_site_views && python manage.py test`

- [ ] **Step 7: Commit**

```bash
git add blog/site_views.py blog/urls_site.py blog/templates/blog/post_list.html blog/templates/blog/_post_cards.html blog/tests/test_site_views.py static/js/htmx.min.js fortkentcinema/urls.py templates/base.html
git commit -m "feat(blog): /blog list page with HTMX infinite scroll (vendored htmx)"
```

---

### Task 4: Blog detail page (`/blog/<slug>`) — the OG-tag fix

`PostDetailView` renders a single post with **per-post server-rendered meta/OG tags** (title, description, `og:image` = the post's header image, `og:type=article`, canonical) — solving the original problem where shared blog links showed the site default. Content renders as paragraphs; a copy-link button uses Alpine.

**Files:**
- Create: `blog/templates/blog/post_detail.html`
- Modify: `blog/site_views.py` (add `PostDetailView`), `blog/urls_site.py` (add the route), `blog/tests/test_site_views.py`
- Reference: SPA `src/pages/BlogDetailPage.jsx`

**Interfaces:**
- Consumes: `BlogPost` by slug; `blog_extras.excerpt`/`paragraphs`.
- Produces:
  - URL name `blog_detail` at `blog/<slug:slug>`.
  - `PostDetailView(DetailView)`: `model=BlogPost`, `slug_field="slug"`, `slug_url_kwarg="slug"`, `context_object_name="post"`, `template_name="blog/post_detail.html"`; adds `og_image_url` to context = `request.build_absolute_uri(post.header_image.url)` when an image exists, else `None`.

- [ ] **Step 1: Write the failing test**

Add to `blog/tests/test_site_views.py`:

```python
class BlogDetailTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        author = BlogAuthor.objects.create(first_name="Ada", last_name="Lovelace")
        cat = BlogCategory.objects.create(name="News")
        cls.post = BlogPost.objects.create(
            title="Big News", subtitle="A subtitle that describes it",
            author=author, category=cat, post_date="2026-01-15",
            content="First paragraph.\n\nSecond paragraph.",
        )

    def test_detail_200_and_template(self):
        resp = self.client.get(reverse("blog_detail", args=[self.post.slug]))
        self.assertEqual(resp.status_code, 200)
        self.assertTemplateUsed(resp, "blog/post_detail.html")

    def test_unknown_slug_404(self):
        self.assertEqual(self.client.get(reverse("blog_detail", args=["nope"])).status_code, 404)

    def test_per_post_meta_overrides(self):
        html = self.client.get(reverse("blog_detail", args=[self.post.slug])).content.decode()
        self.assertIn("<title>Big News | Fort Kent Cinema</title>", html)
        self.assertIn('property="og:title" content="Big News"', html)
        self.assertIn('property="og:type" content="article"', html)
        # description falls back to the subtitle
        self.assertIn('property="og:description" content="A subtitle that describes it"', html)

    def test_content_renders_paragraphs(self):
        html = self.client.get(reverse("blog_detail", args=[self.post.slug])).content.decode()
        self.assertIn("<p>First paragraph.</p>", html)
        self.assertIn("<p>Second paragraph.</p>", html)
```

- [ ] **Step 2: Run → fail.**

- [ ] **Step 3: Add `PostDetailView`**

Append to `blog/site_views.py`:

```python
from django.views.generic import DetailView


class PostDetailView(DetailView):
    model = BlogPost
    slug_field = "slug"
    slug_url_kwarg = "slug"
    context_object_name = "post"
    template_name = "blog/post_detail.html"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        post = ctx["post"]
        ctx["og_image_url"] = (
            self.request.build_absolute_uri(post.header_image.url)
            if post.header_image else None
        )
        return ctx
```

Add the route to `blog/urls_site.py`:

```python
from .site_views import PostListView, PostDetailView
# ...
    path("<slug:slug>", PostDetailView.as_view(), name="blog_detail"),
```

- [ ] **Step 4: Create `blog/templates/blog/post_detail.html`**

Transcribe `BlogDetailPage.jsx` preserving classes (`blog-detail-page`, `blog-detail-hero`, `blog-detail-hero-img`, `blog-detail-hero-overlay`, `blog-detail-container`, `blog-detail-nav`, `blog-detail-back`, `blog-detail-article`, `blog-detail-header`, `blog-detail-category`, `blog-detail-title`, `blog-detail-subtitle`, `blog-detail-meta`, `blog-detail-author`, `blog-detail-date`, `blog-detail-share`, `blog-detail-body`, `blog-detail-footer`, `blog-detail-footer-link`). Key parts:

```django
{% extends "base.html" %}
{% load static %}{% load blog_extras %}

{% block title %}{{ post.title }} | Fort Kent Cinema{% endblock %}
{% block description %}{% if post.subtitle %}{{ post.subtitle }}{% else %}{{ post.content|excerpt:160 }}{% endif %}{% endblock %}
{% block og_title %}{{ post.title }}{% endblock %}
{% block og_description %}{% if post.subtitle %}{{ post.subtitle }}{% else %}{{ post.content|excerpt:160 }}{% endif %}{% endblock %}
{% block og_type %}article{% endblock %}
{% block og_image %}{% if og_image_url %}{{ og_image_url }}{% else %}{{ block.super }}{% endif %}{% endblock %}

{% block extra_css %}<link rel="stylesheet" href="{% static 'css/BlogDetailPage.css' %}" />{% endblock %}

{% block content %}
<div class="blog-detail-page" x-data="{ copied: false }">
  {% if post.header_image %}
  <div class="blog-detail-hero">
    <img src="{{ post.header_image.url }}" alt="{{ post.title }}" class="blog-detail-hero-img" />
    <div class="blog-detail-hero-overlay"></div>
  </div>
  {% endif %}
  <div class="blog-detail-container">
    <nav class="blog-detail-nav"><a href="/blog" class="blog-detail-back">&larr; Back to Blog</a></nav>
    <article class="blog-detail-article">
      <header class="blog-detail-header">
        {% if post.category %}<span class="blog-detail-category">{{ post.category.name }}</span>{% endif %}
        <h1 class="blog-detail-title">{{ post.title }}</h1>
        {% if post.subtitle %}<p class="blog-detail-subtitle">{{ post.subtitle }}</p>{% endif %}
        <div class="blog-detail-meta">
          {% if post.author %}<span class="blog-detail-author">By {{ post.author.first_name }} {{ post.author.last_name }}</span>{% endif %}
          <span class="blog-detail-date">{{ post.post_date|date:"l, F j, Y" }}</span>
          <button class="blog-detail-share" aria-label="Copy link to post"
                  @click="navigator.clipboard.writeText(window.location.href); copied = true; setTimeout(() => copied = false, 2000)"
                  x-text="copied ? 'Copied!' : 'Copy Link'">Copy Link</button>
        </div>
      </header>
      <div class="blog-detail-body">
        {% for para in post.content|paragraphs %}<p>{{ para }}</p>{% endfor %}
      </div>
    </article>
    <footer class="blog-detail-footer"><a href="/blog" class="blog-detail-footer-link">&larr; Back to all posts</a></footer>
  </div>
</div>
{% endblock %}
```

Notes: `date:"l, F j, Y"` matches the SPA's "Weekday, Month D, Year". `og:image` uses `{{ block.super }}` to fall back to the site default when a post has no image. The copy-link is Alpine (`navigator.clipboard` + a 2s "Copied!" toggle) — same behavior as the React `handleCopyLink`.

- [ ] **Step 5: Run → pass**, then full suite.

Run: `python manage.py test blog.tests.test_site_views && python manage.py test`

- [ ] **Step 6: Manual verification (the whole point of this plan)**

With a post in the DB (create via `python manage.py shell` or admin), `runserver` and confirm: `/blog` lists posts and scrolling loads more; `/blog/<slug>` renders; **view source and confirm the `<head>` contains the post's real `og:title`, `og:description`, `og:image`, and `og:type=article`** — the fix. Note what you verified.

- [ ] **Step 7: Commit**

```bash
git add blog/site_views.py blog/urls_site.py blog/templates/blog/post_detail.html blog/tests/test_site_views.py
git commit -m "feat(blog): /blog/<slug> detail page with per-post server-rendered OG tags"
```

---

## Self-Review

**Spec coverage (design doc Section 2 blog rows + Section 5 SEO):**
- `/blog` `ListView` paginated + HTMX infinite scroll → Task 3. `/blog/<slug>` `DetailView` with per-post OG (the original problem) → Task 4. Both in the `blog` app per the spec.
- Shared `blog_card` partial + content filters → Task 2 (also DRYs the Plan 2 teaser).
- Nav + Footer (spec Section 2 partials, left as stubs in Plan 1) → Task 1.
- HTMX vendored (spec's interactivity stack) → Task 3.
- **Deferred (documented elsewhere):** blog `og:image` uses `request.build_absolute_uri`; the site-wide default `og:image` root-path issue + canonical query-string handling remain Plan 5 (SEO) items. ComingSoon calendar HTMX + classics/membership/rentals/about remain Plan 4.

**Placeholder scan:** No TBDs. The one refactor step (teaser → shared card, Task 2 Step 6) is a concrete, tested DRY change, not hand-waving.

**Type/name consistency:** `excerpt`/`paragraphs` filter names match between `blog_extras.py`, the card/detail templates, and the tests. View names (`PostListView`/`PostDetailView`), URL names (`blog_list`/`blog_detail`), context keys (`posts`, `post`, `page_obj`, `paginator`, `og_image_url`) are consistent across `site_views.py`, `urls_site.py`, templates, and tests. `data-spotlight`/`data-reveal` hooks match the effects scanners. The `_post_cards.html` fragment is used both by the full page (initial render) and the HTMX response (`get_template_names`), so cards/sentinel/count markup lives in exactly one place.
