# Remove Sponsorship Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Delete film sponsorship from the site: the `/sponsor/` page, inquiries, the studio catalog, the sponsored banner and the Support strip. Rentals must not change.

**Architecture:** First decouple rentals from sponsorship code (the status enum and the form CSS). Then delete outward-in, from public site to home page to dashboard, then admin and commands, and finally the models with one new migration that drops three tables. The full suite is green after every task.

**Tech Stack:** Django (`python manage.py test`), Alpine/HTMX templates, CSS bundled by esbuild (`cd frontend && npm run build:css`), Playwright for screenshots.

**Spec:** `docs/superpowers/specs/2026-10-13-remove-sponsorship-design.md`

## Global Constraints

- Branch `feat/remove-sponsorship`. Commit after each task. Do not merge or push.
- Drop the tables with no data export (owner's decision).
- `/sponsor/`, `/sponsor/inquire`, `/sponsor/catalog` and `/sponsor/films` must return a plain 404. No redirect.
- Never edit or delete existing migrations 0001–0023. 0010 depends on 0009.
- Rentals must render and behave identically: same statuses (NEW/CONTACTED/WON/LOST) and a pixel-identical `/rentals/` form.
- Rebuild `static/css/bundle.css` whenever a CSS file or `frontend/styles/main.css` changes. It is committed.
- Comments that would point at deleted code get reworded; don't leave dangling references to `/sponsor/`. History in `docs/` stays.
- Test command: `python manage.py test` (full suite takes ~4–5 min). Use a test label for single files.

## Review Focus

1. **An old bookmark or Google result for `/sponsor/?sort=title` or `/sponsor/catalog?q=x`** should get a 404, not a 500. Task 3's removal test covers query strings.
2. **Rental inquiries already saved with status CONTACTED/WON/LOST** must still display and change status in the dashboard after the enum moves. Task 1 tests a status change on an existing row.
3. **The dashboard home with leftover NEW rental inquiries and voicemails** must still show those alerts once the sponsorship alert is gone. Task 5 tests the rental alert count on its own.
4. **A Film that had StudioTitle rows** must still load its admin page and its public movie page after the migration. Task 7 creates a film with a title before migrating back and forward.
5. **The rental form's error and "sent" states** (not just the empty form) must keep their styling. Task 2 screenshots an invalid submit and a successful submit.

---

### Task 1: Move `InquiryStatus` into the rental model

**Files:**
- Modify: `cinema/models/rental_inquiry.py` (define the enum here), `cinema/models/sponsorship_inquiry.py` (import it from rental_inquiry for now), `cinema/models/__init__.py` (export from rental_inquiry)
- Modify: every importer of `InquiryStatus` that names the sponsorship module (`grep -rn "sponsorship_inquiry import InquiryStatus"`)
- Test: `cinema/tests/test_rental_inquiry_status.py` (new)

**Interfaces:**
- Produces: `cinema.models.InquiryStatus` (TextChoices NEW/CONTACTED/WON/LOST, labels "New"/"Contacted"/"Won"/"Lost"), defined in `cinema/models/rental_inquiry.py`

- [ ] **Step 1: Write the failing test**

```python
class InquiryStatusHomeTests(TestCase):
    def test_enum_lives_with_rentals(self):
        from cinema.models import rental_inquiry
        self.assertEqual(rental_inquiry.InquiryStatus.__module__, "cinema.models.rental_inquiry")
        self.assertEqual([c for c, _ in rental_inquiry.InquiryStatus.choices],
                         ["NEW", "CONTACTED", "WON", "LOST"])

    def test_existing_row_keeps_and_changes_status(self):
        # Review Focus 2
        r = RentalInquiry.objects.create(contact_name="A", email="a@b.c", status="WON")
        staff = get_user_model().objects.create_user(username="staff", password="pw", is_staff=True)
        self.client.force_login(staff)
        self.client.post(reverse("dashboard:rental_inquiry_status", args=[r.pk]),
                         {"status": "CONTACTED"})
        r.refresh_from_db()
        self.assertEqual(r.status, "CONTACTED")
```

- [ ] **Step 2: Run it** with `python manage.py test cinema.tests.test_rental_inquiry_status`. Expected: FAIL on `__module__`.
- [ ] **Step 3: Move the class.** Leave `sponsorship_inquiry.py` importing it so that file keeps working until Task 7.
- [ ] **Step 4: Run** the new test plus `web.tests.test_rental_inquiry dashboard`. Expected: PASS. `python manage.py makemigrations --check --dry-run` shows no changes.
- [ ] **Step 5: Commit** `refactor(rentals): own the inquiry status enum`.

### Task 2: Give the rental form its own styles

**Files:**
- Modify: `templates/partials/rental_inquiry_form.html` (6 classes `sponsor-inquire__{form,field,label,error,field-error,sent}` become `rental-inquire__…`)
- Modify: `static/css/PrivateRentalsPage.css` (receives the rules; line ~234 builds on them), `static/css/SponsorPage.css` (loses the rules that are now rental's), `static/css/bundle.css` (rebuilt)
- Test: `web/tests/test_rental_inquiry.py`

**Interfaces:**
- Produces: CSS classes `rental-inquire__form`, `__field`, `__label`, `__error`, `__field-error`, `__sent`

- [ ] **Step 1: Take "before" screenshots** of `/rentals/` at 1280×800 and 390×844. Capture the empty form, the form after an invalid submit (Review Focus 5), and the HTMX "sent" state after a valid submit. Run the server on port 8765 and save the shots to the scratchpad.
- [ ] **Step 2: Write the failing test** `test_form_uses_rental_classes`. It renders `/rentals/` and asserts `rental-inquire__form` is in the HTML and `sponsor-inquire` is not.
- [ ] **Step 3: Run it.** Expected: FAIL.
- [ ] **Step 4: Move every rule in `SponsorPage.css`** whose selector targets only those six classes (~lines 593–740; descendant selectors such as `.sponsor-inquire__form input` count) into `PrivateRentalsPage.css`, renamed. Rename the six classes in the template. If a moved rule also lists a sponsor-only selector, split it so the sponsor copy stays until Task 3. Rebuild the bundle.
- [ ] **Step 5: Run** `web.tests.test_rental_inquiry web.tests.test_performance`. Expected: PASS.
- [ ] **Step 6: Take "after" screenshots** of the same three states and compare them with the "before" shots. Any visible difference is a bug; fix it before committing.
- [ ] **Step 7: Commit** `refactor(rentals): own the inquiry form styles`.

### Task 3: Remove the public sponsor page

**Files:**
- Create: `web/tests/test_sponsorship_removed.py`, `web/tests/test_sitemap_lastmod.py` (receives `StaticSitemapLastmodTests` verbatim from `test_sponsor_seo.py`)
- Delete: `web/templates/web/sponsor.html`, `templates/partials/sponsor_catalog.html`, `sponsor_film_options.html`, `sponsor_inquiry_form.html`, `static/css/SponsorPage.css`, `static/img/og-sponsor.jpg`, `web/tests/test_sponsor.py`, `test_sponsor_inquiry.py`, `test_sponsor_seo.py`
- Modify: `web/urls.py` (4 sponsor routes), `web/views.py` (`SPONSOR_SORTS`, `SponsorCatalogMixin`, `SponsorView`, `SponsorCatalogView`, `SponsorFilmOptionsView`, `SponsorInquiryView`, `LlmsTxtView` `sponsor_from`, now-unused imports), `web/forms.py` (`SponsorshipInquiryForm`, `StudioTitle` import), `web/sitemaps.py`, `templates/llms.txt` (sponsor line; heading becomes "Rentals, gift cards"), `templates/partials/coming_soon.html` ("Pick a film and sponsor it" item), `templates/base.html:21` comment, `frontend/styles/main.css`, `web/constants.py` (`SPONSORSHIP_POPCORN_CAP`, `SPONSORSHIP_SHOWCASE`, `SPONSORSHIP_FAQ`; keep `SPONSORSHIP_TIERS` and `SPONSORSHIP_TIER_LABELS` until Tasks 4–5 remove their last users), tests in `test_llms_txt.py`, `test_nav.py:69-87`, `test_home_appendix.py:106-107`

**Interfaces:**
- Consumes: Task 2 (rental styles no longer in SponsorPage.css)

- [ ] **Step 1: Write the failing tests** in `test_sponsorship_removed.py`:

```python
class SponsorPageRemovedTests(TestCase):
    def test_pages_are_404(self):
        for path in ("/sponsor/", "/sponsor/inquire", "/sponsor/catalog",
                     "/sponsor/films", "/sponsor/?sort=title", "/sponsor/catalog?q=x"):
            self.assertEqual(self.client.get(path).status_code, 404, path)
    def test_route_names_gone(self):
        for name in ("sponsor", "sponsor_inquire", "sponsor_catalog", "sponsor_films"):
            with self.assertRaises(NoReverseMatch):
                reverse(name)
    def test_not_in_sitemap(self):
        self.assertNotContains(self.client.get("/sitemap.xml"), "/sponsor")
    def test_not_in_llms_txt(self):
        body = self.client.get("/llms.txt").content.decode().lower()
        self.assertNotIn("sponsor", body)
    def test_coming_soon_empty_state_has_no_sponsor_link(self):
        # home with no coming-soon films (mock get_coming_soon -> [])
        self.assertNotIn("sponsor it", html)
```

- [ ] **Step 2: Run it.** Expected: FAIL (pages are 200).
- [ ] **Step 3: Move `StaticSitemapLastmodTests`** into `test_sitemap_lastmod.py` with its imports, and run it. Expected: PASS before any deletion.
- [ ] **Step 4: Delete and edit** the files listed above. In `test_nav.py`, keep the footer and nav assertions that `/sponsor/` is absent. Delete only the parts that reference the page's existence. Remove the `test_llms_txt.py` sponsor-price assertion (line ~61). Rebuild the bundle.
- [ ] **Step 5: Run** `web` and `blog`. Expected: PASS. `grep -rn "url 'sponsor'\|reverse(\"sponsor" templates web blog dashboard` returns nothing.
- [ ] **Step 6: Commit** `feat: remove the /sponsor/ page`.

### Task 4: Remove the sponsored banner and the Support strip

**Files:**
- Delete: `templates/partials/cta_sponsored.html`, `cta_sponsor.html`, `home_support.html`, `cta_donate.html`, `static/css/SponsoredCTA.css`, `web/tests/test_sponsored_screening.py`, `web/tests/test_donate_cta.py`
- Modify: `templates/partials/now_showing.html:12` (include), `web/templates/web/home.html` (support include at ~40 and composition comment rows 20–30), `web/views.py` (`sponsored_screening()`, HomeView keys `sponsored`, `show_support`, `sponsorship_from_price`, the donate key), `static/css/HomeSections.css` (Support strip and `.sponsor-cta`/`.donate-cta` rules), `frontend/styles/main.css`, `web/constants.py` (`SPONSORED_SCREENING`, `SHOW_SUPPORT_STRIP`, `DONATION`, `SPONSORSHIP_TIERS`), `web/tests/test_home_sections.py` (import line 34, section lists 38/44, 139–151, 186–203, `SponsorCtaCopyTests` 394–445, `SupportTests` 552–575), `web/tests/test_performance.py:115`

- [ ] **Step 1: Add failing tests** to `test_sponsorship_removed.py`: `test_home_has_no_banner_or_support_strip` asserts that `sponsored-cta`, `id="support"`, `sponsor_click`, `donate_click` and `sponsored_cta_click` do not appear in the home HTML. Also add `test_constants_gone`, which asserts `web.constants` has no `SPONSORED_SCREENING`, `SHOW_SUPPORT_STRIP`, `DONATION` or `SPONSORSHIP_TIERS`.
- [ ] **Step 2: Run them.** Expected: FAIL on the constants.
- [ ] **Step 3: Delete and edit** the files listed above. Update the home section-order tests to the real order without `sponsored-cta` and `support`. Rebuild the bundle.
- [ ] **Step 4: Run** `web`. Expected: PASS.
- [ ] **Step 5: Commit** `feat(home): drop the sponsored banner and Support strip`.

### Task 5: Remove the dashboard inquiries screen and alert

**Files:**
- Delete: `dashboard/inquiry_views.py`, `dashboard/templates/dashboard/inquiries.html`, `dashboard/tests/test_inquiries.py`
- Modify: `dashboard/urls.py` (import line 5, routes 287–292), `dashboard/templates/dashboard/_sidebar.html:14-15`, `dashboard/views.py:14,18,96-98`, `dashboard/smart_alerts.py` (`new_inquiries` param and the `new-sponsorship-inquiries` block at 51–56), `web/constants.py` (`SPONSORSHIP_TIER_LABELS`), `dashboard/tests/test_smart_alerts.py` (`InquiryAlertTests` 69–98, and lines 122–129 that combine both counts)

**Interfaces:**
- Produces: `build_smart_alerts(engagements, tomorrow_showtimes_count, today, new_rental_inquiries=0, new_voicemails=0, square_pull_status=None, square_sync_failures=0, square_membership_failures=0)`. Only `new_inquiries` is removed; every other parameter is unchanged.

- [ ] **Step 1: Add failing tests.** In `test_sponsorship_removed.py`, `test_dashboard_inquiries_gone` asserts that `reverse("dashboard:inquiries")` raises `NoReverseMatch`, and that the staff dashboard home HTML has no `href` to `/dashboard/inquiries` while it still contains the "Rental Inquiries" link. In `test_smart_alerts.py`, `test_rental_alert_alone` (Review Focus 3) checks that `build_smart_alerts(..., new_rental_inquiries=2, new_voicemails=1)` yields both alerts and no `new-sponsorship-inquiries` id, and that passing `new_inquiries=` raises `TypeError`.
- [ ] **Step 2: Run them.** Expected: FAIL.
- [ ] **Step 3: Delete and edit** the files listed above.
- [ ] **Step 4: Run** `dashboard web`. Expected: PASS.
- [ ] **Step 5: Commit** `feat(dashboard): drop sponsorship inquiries`.

### Task 6: Remove the catalog admin, the import command and promo cards

**Files:**
- Delete: `cinema/management/commands/import_studio_catalog.py`, `cinema/studio_import.py`, `cinema/studio_catalog.py`, `cinema/forms.py`, `cinema/management/commands/render_promo_cards.py`, `cinema/social_cards/promo.py`, `templates/admin/cinema/studiotitle/` (both templates), `cinema/tests/test_import_studio_catalog.py`, `test_studio_import.py`, `test_studio_catalog.py`, `test_admin_catalog_import.py`
- Modify: `cinema/admin.py` (imports 26–28; `StudioAdmin`, `StudioTitleAdmin` with its import URL/view, `SponsorshipInquiryAdmin`)

- [ ] **Step 1: Add failing tests** to `test_sponsorship_removed.py`. `test_commands_gone` uses `call_command("import_studio_catalog")` and `call_command("render_promo_cards")`, and each must raise `CommandError` ("Unknown command"). `test_admin_unregistered` asserts that `admin.site.is_registered(m)` is False for Studio, StudioTitle and SponsorshipInquiry, imported from `cinema.models` while they still exist.
- [ ] **Step 2: Run them.** Expected: FAIL.
- [ ] **Step 3: Delete and edit** the files listed above. `grep -rn "studio_import\|studio_catalog\|social_cards.promo\|StudioCatalogImportForm" --include=*.py .` (excluding `.venv`) returns nothing.
- [ ] **Step 4: Run** `cinema web`. Expected: PASS.
- [ ] **Step 5: Commit** `feat(admin): drop the studio catalog import and promo cards`.

### Task 7: Delete the models and add migration 0024

**Files:**
- Delete: `cinema/models/sponsorship_inquiry.py`, `cinema/models/studio.py`, `cinema/models/studio_title.py`, `cinema/tests/test_studio_models.py`
- Create: `cinema/migrations/0024_remove_sponsorship.py` (generated)
- Modify: `cinema/models/__init__.py` (exports), `cinema/screen_capacity.py:4` docstring (say capacity is the screen's seat count, without the sponsorship reason), `web/tests/test_sponsorship_removed.py` (drop the model imports Task 6 used and assert by app registry instead), `web/tests/test_rental_inquiry.py:93` comment

- [ ] **Step 1: Write the failing test** `test_models_gone`. For each name in "Studio", "StudioTitle" and "SponsorshipInquiry", `apps.get_model("cinema", name)` raises `LookupError`. Also check `"studio_titles"` is not in `[f.name for f in Film._meta.get_fields()]`.
- [ ] **Step 2: Run it.** Expected: FAIL.
- [ ] **Step 3: Delete the three model files, update the exports and generate the migration:** `python manage.py makemigrations cinema --name remove_sponsorship`. Open the file and check it contains only `RemoveField`/`DeleteModel` operations for those three models, ordered SponsorshipInquiry → StudioTitle → Studio. No `RentalInquiry` or `Film` field changes.
- [ ] **Step 4: Run** `python manage.py makemigrations --check --dry-run` (expect "No changes detected"), then `python manage.py test`. Expected: full suite PASS.
- [ ] **Step 5: Run a round trip on a scratch database** (Review Focus 4). Copy the dev DB, or point settings at a temp sqlite. Run `migrate cinema 0023`, create a Film with a Studio and StudioTitle linked to it, then `migrate cinema 0024`. The film's admin change page and `/movies/<slug>/` both return 200. Then `migrate cinema 0023` again, which succeeds with empty tables. Leave the dev DB at 0024.
- [ ] **Step 6: Commit** `feat(cinema): drop sponsorship and studio catalog models`.

### Task 8: Final sweep and verification

**Files:**
- Modify: stale comment-only mentions found by the grep below (`MembershipFAQ.css:58-78`, `PrivateRentalsPage.css:173,233`, `variables.css:104,107`, `global.css:85`, `Nav.css:250`, `rentals.html:14`, `heckle_night.html:14`, `phone/models/voicemail.py:17`, `web/constants.py` leftovers). Reword or remove any comment that points at the deleted page. A `--color-burgundy` that only `/sponsor/` used goes only if nothing else references it.

- [ ] **Step 1: Run** `grep -rni "sponsor" --exclude-dir=.venv --exclude-dir=node_modules --exclude-dir=.git --exclude-dir=staticfiles --exclude-dir=docs --exclude=bundle.css --exclude=package-lock.json .`. Every remaining hit is either the removal tests or a deliberate historical note. Fix the rest.
- [ ] **Step 2: Rebuild the bundle, then run** `python manage.py test` and `python manage.py check`. Expected: all PASS, no issues.
- [ ] **Step 3: Take screenshots** of the home page (desktop and phone), `/rentals/` (compare with Task 2's "before" shots once more) and the staff dashboard home. Nothing is broken or empty.
- [ ] **Step 4: Commit** `chore: sweep sponsorship leftovers`. Then stop and report to the owner without merging.
