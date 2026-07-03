# Django Migration — Plan 5: SEO, E2E & Cutover Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Finish the migration: add a sitemap + robots.txt, resolve the SEO polish items deferred through Plans 1–4 (absolute `og:image`, clean canonical/`og:url`, safe JSON-LD, correct absolute URLs behind the TLS proxy), add a graceful Selenium E2E harness for the JS-driven flows, harden production settings, and produce a **cutover runbook**. The cutover itself (running ansible against production) is **NOT executed by this plan** — it is a documented, human-gated step.

**Architecture:** Sitemaps via `django.contrib.sitemaps` (a `StaticViewSitemap` for fixed pages + a `BlogPostSitemap` from the queryset), URL-mounted `sitemap.xml`/`robots.txt`. SEO fixes touch `base.html` + `settings.py`. Selenium tests use `StaticLiveServerTestCase` + headless Chrome, skipping cleanly when no browser/driver is available so `manage.py test` never fails on infra. Cutover reuses the existing ansible `django_app`/`nginx`/`certbot` roles — `www.fortkentcinema.com` already points at the prod EC2 box (currently a static-site entry), so cutover means adding `www`+apex to the Django app's nginx server_names and retiring the static entry — no DNS change.

**Tech Stack:** Django 5.2.3, `django.contrib.sitemaps`, Selenium 4 (Selenium Manager auto-driver), the existing ansible setup. Tests: Django `unittest` + Selenium `StaticLiveServerTestCase`.

## Global Constraints

- Target repo: `api_fortkentcinema_com`, branch `feat/django-frontend-migration` (continues from Plans 1–4). The ansible repo is a SEPARATE repo at `/Users/bgoding/code/SoftwareMaine/ansible` — Task 4 only PROPOSES changes there in a runbook; do not run ansible.
- Django 5.2.3; existing `api/` DRF surface untouched. Activate `.venv` for Django commands; `.env` (gitignored, `DEBUG=True`) auto-loads.
- **Do NOT execute the production cutover** (no `ansible-playbook`, no ssh to the prod box, no DNS changes). Task 4 produces settings + a runbook only.
- Settings read env via `python-decouple` `config(...)`. New prod-only security settings must default to the safe DEV behavior when their env var is absent (so local `DEBUG=True` dev + the test suite are unaffected).
- Absolute-URL correctness: prod serves behind nginx doing TLS termination, so `request.build_absolute_uri` needs `SECURE_PROXY_SSL_HEADER` + `USE_X_FORWARDED_HOST` to emit `https://www.fortkentcinema.com/...` rather than `http://<internal>`.
- Multi-line template comments use `{% comment %}`. TDD: failing test first each task; commit after each green task.
- Known deferred items being resolved here: (a) `og:image` hardcoded to `https://www.fortkentcinema.com/og-image.jpg` (a root path Django won't serve after cutover) → use `{% static %}`; (b) `og:url`/canonical include query strings → strip to path; (c) JSON-LD values not JS-escaped; (d) `get_calendar_month` month-boundary tz edge (optional, low priority).

---

### Task 1: Sitemap + robots.txt

Adds `django.contrib.sitemaps` with a static-pages sitemap + a blog-post sitemap, and a `robots.txt` pointing at the sitemap.

**Files:**
- Create: `web/sitemaps.py`, `web/tests/test_sitemap.py`
- Modify: `fortkentcinema/settings.py` (add `django.contrib.sitemaps` to INSTALLED_APPS), `fortkentcinema/urls.py` (sitemap + robots routes), `blog/models.py` (add `BlogPost.get_absolute_url`)
- Reference: page URL names from `web/urls.py` (`home`, `membership`, `classics`, `rentals`, `about`) + `blog_list`, `blog_detail`.

**Interfaces:**
- Produces:
  - `BlogPost.get_absolute_url() -> "/blog/<slug>"` (via `reverse("blog_detail", ...)`).
  - `web.sitemaps.StaticViewSitemap` (items = the fixed page url-names; `location` = `reverse(name)`), `web.sitemaps.BlogPostSitemap` (queryset = all posts, uses `get_absolute_url`, `lastmod` = `post_date`).
  - `GET /sitemap.xml` (200, XML listing static pages + posts), `GET /robots.txt` (200, `text/plain`, includes `Sitemap:` line).

- [ ] **Step 1: Write the failing test**

Create `web/tests/test_sitemap.py`:

```python
from django.test import TestCase
from blog.models import BlogAuthor, BlogCategory, BlogPost


class SitemapTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        a = BlogAuthor.objects.create(first_name="A", last_name="B")
        c = BlogCategory.objects.create(name="News")
        cls.post = BlogPost.objects.create(title="P1", subtitle="p-one", author=a,
                                           category=c, post_date="2026-01-01", content="x")

    def test_sitemap_lists_static_and_posts(self):
        resp = self.client.get("/sitemap.xml")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp["Content-Type"].split(";")[0], "application/xml")
        body = resp.content.decode()
        self.assertIn("/membership/", body)
        self.assertIn("/blog/", body)
        self.assertIn(f"/blog/{self.post.slug}", body)

    def test_robots_txt(self):
        resp = self.client.get("/robots.txt")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp["Content-Type"].split(";")[0], "text/plain")
        self.assertIn("Sitemap:", resp.content.decode())

    def test_blogpost_get_absolute_url(self):
        self.assertEqual(self.post.get_absolute_url(), f"/blog/{self.post.slug}")
```

- [ ] **Step 2: Run → fail**

Run: `source .venv/bin/activate && python manage.py test web.tests.test_sitemap`
Expected: 404s (no sitemap/robots routes).

- [ ] **Step 3: Add `get_absolute_url` + sitemaps**

`blog/models.py` — add to `BlogPost`:

```python
    def get_absolute_url(self):
        from django.urls import reverse
        return reverse("blog_detail", kwargs={"slug": self.slug})
```

Create `web/sitemaps.py`:

```python
from django.contrib.sitemaps import Sitemap
from django.urls import reverse
from blog.models import BlogPost


class StaticViewSitemap(Sitemap):
    changefreq = "weekly"
    priority = 0.7

    def items(self):
        return ["home", "membership", "classics", "rentals", "about", "blog_list"]

    def location(self, name):
        return reverse(name)


class BlogPostSitemap(Sitemap):
    changefreq = "monthly"
    priority = 0.6

    def items(self):
        return BlogPost.objects.all()

    def lastmod(self, obj):
        return obj.post_date
```

- [ ] **Step 4: Wire settings + urls**

`settings.py` INSTALLED_APPS — add `"django.contrib.sitemaps"`.

`fortkentcinema/urls.py`:

```python
from django.contrib.sitemaps.views import sitemap
from django.views.generic import TemplateView
from web.sitemaps import StaticViewSitemap, BlogPostSitemap

sitemaps = {"static": StaticViewSitemap, "posts": BlogPostSitemap}

urlpatterns += [
    path("sitemap.xml", sitemap, {"sitemaps": sitemaps}, name="django.contrib.sitemaps.views.sitemap"),
    path("robots.txt", TemplateView.as_view(template_name="robots.txt", content_type="text/plain"), name="robots"),
]
```

Create `templates/robots.txt`:

```django
User-agent: *
Allow: /
Sitemap: {{ request.scheme }}://{{ request.get_host }}/sitemap.xml
```

(The sitemap framework builds absolute URLs from the request host when the sites framework isn't installed — no `SITE_ID` needed.)

- [ ] **Step 5: Run → pass**, then full suite (Plan 4 was 77).

- [ ] **Step 6: Commit**

```bash
git add web/sitemaps.py web/tests/test_sitemap.py fortkentcinema/settings.py fortkentcinema/urls.py blog/models.py templates/robots.txt
git commit -m "feat(seo): sitemap.xml + robots.txt (static pages + blog posts)"
```

---

### Task 2: SEO polish — og:image, canonical, JSON-LD, proxy headers

Fixes the four deferred SEO items so link previews and canonical URLs are correct in production behind the TLS proxy.

**Files:**
- Modify: `templates/base.html`, `fortkentcinema/settings.py`
- Modify/Create: `web/tests/test_pages.py` (assertions)

**Interfaces:**
- Produces: `base.html` emitting an absolute `{% static 'img/og-image.jpg' %}` default `og:image`, query-string-free `og:url`/canonical, and JS/JSON-safe JSON-LD; settings honoring `X-Forwarded-Proto`/`X-Forwarded-Host` when `USE_PROXY_HEADERS` env is set.

- [ ] **Step 1: Write the failing test**

Add to `web/tests/test_pages.py` (or a new `test_seo.py`):

```python
class SeoTagTests(TestCase):
    def test_default_og_image_is_static_absolute(self):
        html = self.client.get(reverse("home")).content.decode()
        # default og:image should point at the served static file, not a bare root path
        self.assertIn("/static/img/og-image.jpg", html)
        self.assertNotIn('content="https://www.fortkentcinema.com/og-image.jpg"', html)

    def test_canonical_strips_query_string(self):
        html = self.client.get(reverse("home") + "?utm_source=x").content.decode()
        self.assertNotIn("utm_source", html)          # canonical/og:url must not carry query params
```

- [ ] **Step 2: Run → fail.**

- [ ] **Step 3: Fix `base.html`**

- **Default `og:image`** — change the `og_image` block default from the hardcoded `https://www.fortkentcinema.com/og-image.jpg` to the served static asset, absolute-ised:
  ```django
  <meta property="og:image" content="{% block og_image %}{{ request.scheme }}://{{ request.get_host }}{% static 'img/og-image.jpg' %}{% endblock %}" />
  ```
  (Blog detail already overrides this with `og_image_url`; membership/rentals/about/classics inherit this corrected default.)
- **Canonical + `og:url`** — strip the query string by using the path only:
  ```django
  <link rel="canonical" href="{{ request.scheme }}://{{ request.get_host }}{{ request.path }}" />
  ...
  <meta property="og:url" content="{{ request.scheme }}://{{ request.get_host }}{{ request.path }}" />
  ```
- **JSON-LD safety** — the values interpolated into the `application/ld+json` script (`site_config.cinema.name`, `.phone`, address, `.social.facebook`) are static config with no special chars today, but to be correct emit them via `escapejs` inside the JSON string context:
  ```django
  "name": "{{ site_config.cinema.name|escapejs }}",
  "telephone": "{{ site_config.cinema.phone|escapejs }}",
  ...
  ```
  Apply `|escapejs` to every interpolated value inside the JSON-LD `<script>`.

- [ ] **Step 4: Add proxy-header settings**

In `settings.py`, gate on an env flag so dev/tests are unaffected:

```python
if config("USE_PROXY_HEADERS", default=False, cast=bool):
    SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
    USE_X_FORWARDED_HOST = True
```

(Prod `.env` sets `USE_PROXY_HEADERS=True`; documented in Task 4's runbook.)

- [ ] **Step 5: Run → pass**, then full suite. Confirm blog-detail per-post `og:image` still uses the post image (unchanged) and the home/other pages now emit the static absolute default.

- [ ] **Step 6: Commit**

```bash
git add templates/base.html fortkentcinema/settings.py web/tests/
git commit -m "fix(seo): absolute static og:image, query-free canonical/og:url, escaped JSON-LD, proxy headers"
```

---

### Task 3: Selenium E2E harness (graceful skip)

Adds `StaticLiveServerTestCase` Selenium tests for the JS-driven flows (nav mobile menu, home date-nav + trailer modal, blog infinite scroll, coming-soon calendar toggle). Tests **skip cleanly** when Chrome/driver is unavailable so `manage.py test` never fails on missing infra.

**Files:**
- Create: `web/tests/test_e2e.py`
- Modify: `dev-requirements.txt` (add `selenium`)
- Reference: the pages built in Plans 2–4.

**Interfaces:**
- Produces: `web/tests/test_e2e.py` with a base `SeleniumTestCase(StaticLiveServerTestCase)` that in `setUpClass` tries to start headless Chrome and calls `raise unittest.SkipTest(...)` if it can't; individual tests for the key flows.

- [ ] **Step 1: Add selenium to dev-requirements + install**

Add `selenium==4.25.0` to `dev-requirements.txt`; `pip install selenium==4.25.0` (in venv). Selenium 4 ships **Selenium Manager**, which auto-provisions a chromedriver matching an installed Chrome.

- [ ] **Step 2: Write the harness with graceful skip**

Create `web/tests/test_e2e.py`:

```python
import unittest
from django.contrib.staticfiles.testing import StaticLiveServerTestCase


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


class NavMenuE2E(SeleniumTestCase):
    def test_mobile_menu_toggles(self):
        from selenium.webdriver.common.by import By
        self.driver.set_window_size(500, 900)   # phone width → hamburger visible
        self.driver.get(self.live_server_url + "/")
        links = self.driver.find_element(By.CSS_SELECTOR, ".nav-links")
        self.assertNotIn("nav-links--open", links.get_attribute("class"))
        self.driver.find_element(By.CSS_SELECTOR, ".nav-hamburger").click()
        self.assertIn("nav-links--open", links.get_attribute("class"))
```

Add further tests as separate methods/classes for: blog infinite scroll (seed >6 posts, scroll, assert more cards appear), coming-soon calendar toggle (click calendar btn, assert `.coming-calendar` appears via HTMX), and a home trailer modal open/close. Keep each test resilient (explicit waits via `WebDriverWait`). Seed DB rows with `setUpTestData`/`setUp` as needed. If leprinceos is unreachable in the test env, the home now-showing/coming-soon may be empty — gate those assertions on presence, or use pages that don't need the external API (nav, blog) for the must-pass flows.

- [ ] **Step 3: Run the E2E module**

Run: `python manage.py test web.tests.test_e2e -v 2`
Expected: either the flows PASS (if Chrome is available) or the suite reports **skipped** (not failed). Confirm the whole suite (`python manage.py test`) stays green with E2E either passing or skipped.

- [ ] **Step 4: Commit**

```bash
git add web/tests/test_e2e.py dev-requirements.txt
git commit -m "test(e2e): Selenium harness for nav/blog/calendar flows (skips without Chrome)"
```

---

### Task 4: Production settings hardening + cutover runbook (NO execution)

Adds env-gated production security settings and writes the cutover runbook. **Runs nothing against production.**

**Files:**
- Modify: `fortkentcinema/settings.py` (env-gated prod security), `requirements.txt` (ensure a WSGI server — `gunicorn`)
- Create: `docs/superpowers/plans/cutover-runbook.md`
- Reference (read-only): `/Users/bgoding/code/SoftwareMaine/ansible/site.yml`, `ansible/group_vars/webservers.yml`, `ansible/roles/{django_app,nginx,certbot}` (to describe the exact changes).

**Interfaces:**
- Produces: env-gated `SECURE_SSL_REDIRECT`, `SESSION_COOKIE_SECURE`, `CSRF_COOKIE_SECURE`, `CSRF_TRUSTED_ORIGINS`, HSTS (all off by default so dev/tests unaffected); `gunicorn` in requirements; a step-by-step cutover runbook.

- [ ] **Step 1: Write the failing settings test**

Add to `web/tests/test_settings.py`:

```python
class ProdSecuritySettingsTests(SimpleTestCase):
    def test_security_settings_default_off_for_dev(self):
        # With no prod env vars set (dev/test), these stay dev-safe.
        from django.conf import settings
        self.assertFalse(getattr(settings, "SECURE_SSL_REDIRECT", False))

    def test_csrf_trusted_origins_configurable(self):
        # The setting exists (possibly empty) and is a list.
        from django.conf import settings
        self.assertIsInstance(getattr(settings, "CSRF_TRUSTED_ORIGINS", []), list)
```

- [ ] **Step 2: Run → fail** (if `CSRF_TRUSTED_ORIGINS` unset).

- [ ] **Step 3: Add env-gated prod security to settings**

```python
SECURE_SSL_REDIRECT = config("SECURE_SSL_REDIRECT", default=False, cast=bool)
SESSION_COOKIE_SECURE = config("SESSION_COOKIE_SECURE", default=False, cast=bool)
CSRF_COOKIE_SECURE = config("CSRF_COOKIE_SECURE", default=False, cast=bool)
CSRF_TRUSTED_ORIGINS = config("CSRF_TRUSTED_ORIGINS", default="", cast=Csv())
SECURE_HSTS_SECONDS = config("SECURE_HSTS_SECONDS", default=0, cast=int)
SECURE_HSTS_INCLUDE_SUBDOMAINS = config("SECURE_HSTS_INCLUDE_SUBDOMAINS", default=False, cast=bool)
SECURE_HSTS_PRELOAD = config("SECURE_HSTS_PRELOAD", default=False, cast=bool)
```

(`Csv` is already imported.) Add `gunicorn==23.0.0` to `requirements.txt` under the ASGI/WSGI server section.

- [ ] **Step 4: Run → pass**, then full suite.

- [ ] **Step 5: Write the cutover runbook**

Create `docs/superpowers/plans/cutover-runbook.md` documenting (do NOT execute):

1. **Pre-flight:** merge `feat/django-frontend-migration` → the branch the deploy pulls (main), or point the deploy at the feature branch. Confirm full suite green + `collectstatic` clean.
2. **Prod env** (on the box / vaulted `env_vars` for the `api_fortkentcinema_com` django_app): `DEBUG=False`; `ALLOWED_HOSTS=www.fortkentcinema.com,fortkentcinema.com,api.fortkentcinema.com`; `USE_PROXY_HEADERS=True`; `SECURE_SSL_REDIRECT=True`; `SESSION_COOKIE_SECURE=True`; `CSRF_COOKIE_SECURE=True`; `CSRF_TRUSTED_ORIGINS=https://www.fortkentcinema.com,https://fortkentcinema.com,https://api.fortkentcinema.com`; `SECURE_HSTS_SECONDS=31536000`; the existing DB/`SECRET_KEY`/`ENABLE_CDN` values; leprinceos base URL default.
3. **ansible change** (in the `ansible` repo — propose as a diff, human applies): add `www.fortkentcinema.com` + `fortkentcinema.com` to the `api_fortkentcinema_com` **django_app** `server_names` (with the apex→www 301 like the current static entry), and **remove** the `www_fortkentcinema_com` entry from `static_sites` in `group_vars/webservers.yml`. Since `www` already resolves to this box, this is an nginx/cert reconfig, not a DNS change.
4. **Deploy:** `ansible-playbook site.yml --tags deploy,nginx,certbot -e deploy_app=api_fortkentcinema_com` (adjust to the role's real invocation), which runs `collectstatic` + gunicorn restart + nginx reload + certbot for the added names.
5. **Verify:** `https://www.fortkentcinema.com/` serves the Django home; `/blog/<slug>` shows per-post OG tags (`curl | grep og:`); `/sitemap.xml` + `/robots.txt` resolve; `https://fortkentcinema.com` 301→www; `api.fortkentcinema.com/api/posts/` still works.
6. **Rollback:** re-add the `www_fortkentcinema_com` static_sites entry + remove www/apex from the django_app server_names, re-run the nginx tag. (The React build is still deployed; this restores it.)

- [ ] **Step 6: Commit**

```bash
git add fortkentcinema/settings.py requirements.txt docs/superpowers/plans/cutover-runbook.md
git commit -m "feat(deploy): env-gated prod security settings + gunicorn + cutover runbook"
```

---

## Self-Review

**Spec coverage (design doc Section 5 SEO + Section 7 cutover):**
- Sitemap + robots (spec Section 5) → Task 1. Absolute og:image / canonical / JSON-LD / proxy headers (deferred items) → Task 2. Selenium E2E (spec Section 6 testing) → Task 3. Prod security + deployment/cutover (spec Section 7) → Task 4 (runbook; **execution is human-gated, per the plan's Goal**).
- After this plan the migration is code-complete; only the human-run cutover remains.

**Placeholder scan:** No TBDs. Task 3's E2E tests intentionally skip-not-fail without a browser (documented behavior, not a placeholder). Task 4 explicitly produces a runbook rather than executing — the "do not run ansible" boundary is stated in the Goal and Global Constraints.

**Type/name consistency:** sitemap url-names (`home`, `membership`, `classics`, `rentals`, `about`, `blog_list`, `blog_detail`) match `web/urls.py`/`blog/urls_site.py`. `BlogPost.get_absolute_url` used by `BlogPostSitemap`. New settings are all env-gated with dev-safe defaults, matching the "dev/tests unaffected" constraint. The cutover runbook's env vars line up with the settings added in Tasks 2 + 4 (`USE_PROXY_HEADERS`, `SECURE_SSL_REDIRECT`, `CSRF_TRUSTED_ORIGINS`, etc.).
