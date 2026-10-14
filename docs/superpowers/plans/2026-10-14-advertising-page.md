# Advertising Page Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A public `/advertise/` page selling two monthly pre-show ad products, with an inquiry form whose rows land in the dashboard like rental inquiries.

**Architecture:** A sibling of the rentals flow, copied and trimmed, nothing shared beyond `InquiryStatus`. The model and form land first because the page template includes the form; the page, the dashboard, and the site wiring follow, each a green commit. Prices, the video cap and the artwork deadline live in `web/constants.py` and every rendering reads them.

**Tech Stack:** Django 5.2, SQLite locally, htmx + Alpine dashboard, esbuild CSS bundle, `manage.py test` + `flake8`.

**Spec:** `docs/superpowers/specs/2026-10-14-advertising-page-design.md`

## Global Constraints

- Tests: `.venv/bin/python manage.py test <label> -v 2`. Full suite: `.venv/bin/python manage.py test`. Lint: `.venv/bin/flake8` (the baseline is dirty; the gate is no new findings on changed lines).
- Work on branch `feat/advertise-page` off `main`. Commit per task; do not merge or push unless asked. The owner deploys.
- Prices and terms, verbatim from the spec: slide `$75` a month, video spot `$150` a month, video up to `30` seconds, artwork due by the `20th`, on screen the `1st`. Square invoice each month. No contract, no discounts. Right to refuse any ad; no political ads. Exposure copy: "before every show, from when doors open 30 minutes before showtime". No counts.
- Artwork specs, verbatim: slides `1920 × 1080 PNG or JPEG`; video `MP4, 1920 × 1080, up to 30 seconds`.
- No mail is sent anywhere. The row is the notification.
- Migration numbering: `cinema` is at `0027_remove_film_review`. The new one is `0028_adinquiry` and contains only the new model.
- The rentals flow (`RentalInquiry`, its form, views, templates, CSS, tests) is not touched.
- CSS lives in `static/css/`, every file is imported in `frontend/styles/main.css`, and the bundle is rebuilt with `cd frontend && npm run build:css`.
- `SITE_CONFIG["footer_navigation"]` is alphabetical by label; "Advertise" is first.
- Commit order deviates from the spec's by one swap: model and form before the page, because the page template includes the form.

## Review Focus

1. A POST with `ad_type=BILLBOARD` (not a choice): form error, no row saved (Task 3, `test_bogus_ad_type_is_rejected`).
2. A POST whose `business_name` is only spaces: rejected as required, no row saved (Task 3, `test_blank_business_name_is_rejected`).
3. A 2,001-character message: rejected with the "2,000 characters" error, no row saved (Task 3, `test_overlength_message_is_rejected`).
4. A message containing `<script>` shown in the dashboard list: rendered escaped, never as markup (Task 4, `test_message_is_escaped`).
5. A malformed `X-Forwarded-For` header on the POST: 302 and a row with `ip=None`, not a 500 (Task 3, `test_malformed_forwarded_header_does_not_500`).

---

### Task 1: `AdInquiry` model, migration and admin

**Files:**
- Create: `cinema/models/ad_inquiry.py`
- Create: `cinema/migrations/0028_adinquiry.py` (generated)
- Modify: `cinema/models/__init__.py:5,21-22` (import and `__all__`)
- Modify: `cinema/admin.py:79-87` (add a registration after `RentalInquiryAdmin`)
- Test: `cinema/tests/test_ad_inquiry_model.py`

**Interfaces:**
- Consumes: `InquiryStatus` from `cinema/models/rental_inquiry.py`.
- Produces: `cinema.models.AdType` (`TextChoices`: `SLIDE="SLIDE"` "Pre-show slide", `VIDEO="VIDEO"` "Video spot", `UNSURE="UNSURE"` "Not sure yet") and `cinema.models.AdInquiry` with fields `business_name: CharField(200)`, `contact_name: CharField(200)`, `email: EmailField`, `phone: CharField(40, blank=True)`, `ad_type: CharField(10, choices=AdType.choices, default=AdType.UNSURE)`, `message: TextField(blank=True)`, `status: CharField(20, choices=InquiryStatus.choices, default=InquiryStatus.NEW)`, `created_at: DateTimeField(auto_now_add=True)`, `ip: GenericIPAddressField(null=True, blank=True)`. `Meta.ordering = ["-created_at"]`, `verbose_name_plural = "Ad inquiries"`. `__str__` returns `f"{self.business_name} ({self.get_status_display()})"`.

- [ ] **Step 1: Write the failing tests**

```python
# cinema/tests/test_ad_inquiry_model.py
from cinema.models import AdInquiry, AdType, InquiryStatus
from django.test import TestCase


class AdInquiryModelTests(TestCase):
    def test_defaults(self):
        row = AdInquiry.objects.create(
            business_name="Rock's Diner", contact_name="Pat", email="pat@example.com"
        )
        self.assertEqual(row.ad_type, AdType.UNSURE)
        self.assertEqual(row.status, InquiryStatus.NEW)
        self.assertEqual(row.phone, "")
        self.assertEqual(row.message, "")
        self.assertIsNone(row.ip)
        self.assertEqual(str(row), "Rock's Diner (New)")

    def test_newest_first(self):
        first = AdInquiry.objects.create(business_name="A", contact_name="a", email="a@example.com")
        second = AdInquiry.objects.create(business_name="B", contact_name="b", email="b@example.com")
        self.assertEqual(list(AdInquiry.objects.all()), [second, first])

    def test_ad_type_labels(self):
        self.assertEqual(
            AdType.choices,
            [("SLIDE", "Pre-show slide"), ("VIDEO", "Video spot"), ("UNSURE", "Not sure yet")],
        )
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `.venv/bin/python manage.py test cinema.tests.test_ad_inquiry_model -v 2`
Expected: FAIL with `ImportError: cannot import name 'AdInquiry'`

- [ ] **Step 3: Create `cinema/models/ad_inquiry.py` with `AdType` and `AdInquiry` as specified in Interfaces**

Docstring on the model, in the house style of `RentalInquiry`: the row is the notification; the dashboard lists it and the smart-alert strip counts the NEW ones.

- [ ] **Step 4: Export both from `cinema/models/__init__.py`**

Add `from .ad_inquiry import AdInquiry, AdType` next to the rental import, and both names to `__all__`.

- [ ] **Step 5: Generate the migration**

Run: `.venv/bin/python manage.py makemigrations cinema -n adinquiry`
Expected: creates `cinema/migrations/0028_adinquiry.py` with one `CreateModel("AdInquiry", ...)` and nothing else. Open it and confirm.

- [ ] **Step 6: Register the admin in `cinema/admin.py`**

After `RentalInquiryAdmin`: `@admin.register(AdInquiry)` `class AdInquiryAdmin(admin.ModelAdmin)` with `list_display = ("business_name", "contact_name", "email", "ad_type", "status", "created_at")`, `list_filter = ("status", "ad_type")`, `search_fields = ("business_name", "contact_name", "email")`, `readonly_fields = ("created_at", "ip")`. Add `AdInquiry` to the models import.

- [ ] **Step 7: Run the tests and the migration check**

Run: `.venv/bin/python manage.py test cinema.tests.test_ad_inquiry_model -v 2 && .venv/bin/python manage.py makemigrations --check --dry-run`
Expected: 3 tests PASS; "No changes detected".

- [ ] **Step 8: Commit**

```bash
git add cinema/models/ad_inquiry.py cinema/models/__init__.py cinema/migrations/0028_adinquiry.py cinema/admin.py cinema/tests/test_ad_inquiry_model.py
git commit -m "feat(cinema): AdInquiry model for advertising leads"
```

---

### Task 2: Advertising constants and `AdInquiryForm`

**Files:**
- Modify: `web/constants.py` (after `RENTALS_FAQ`, around line 195)
- Modify: `web/forms.py` (after `RentalInquiryForm`)
- Test: `web/tests/test_ad_inquiry_form.py`

**Interfaces:**
- Consumes: `AdInquiry`, `AdType` from Task 1.
- Produces in `web/constants.py`: `AD_SLIDE_PRICE = 75`, `AD_VIDEO_PRICE = 150`, `AD_VIDEO_MAX_SECONDS = 30`, `AD_ARTWORK_DEADLINE_DAY = 20`, `ADVERTISING_FAQ: list[dict]` (six `{"question", "answer"}` items, in order and with this exact copy, numbers interpolated from the constants above):
  1. "When does my ad start?" — "Ads run by calendar month. Send us your artwork by the 20th and it plays from the 1st of the next month."
  2. "How do I pay?" — "We send a Square invoice each month. Pay online by card, or at the box office."
  3. "Can I change my ad?" — "Yes. Send new artwork by the 20th and it swaps in on the 1st."
  4. "What are the specs?" — "Slides: 1920 × 1080 PNG or JPEG. Video: MP4, 1920 × 1080, up to 30 seconds. We'll check it and send you a proof."
  5. "Is there a contract?" — "No. It's month to month — stop whenever you like."
  6. "Do you run every ad?" — "We reserve the right to decline any ad, and we don't run political ads."
- Produces in `web/forms.py`: `AdInquiryForm(forms.ModelForm)` over `AdInquiry`, fields `["business_name", "contact_name", "email", "phone", "ad_type", "message"]`. Labels: "Business name", "Your name", "Email", "Phone (optional)", "What are you interested in?", "Anything else? (optional)". Hidden honeypot `website = forms.CharField(required=False, widget=forms.HiddenInput)` and `is_bot` property, identical to the rentals form. `ad_type` is rebuilt in `__init__` as `forms.ChoiceField(required=False, widget=forms.RadioSelect, initial=AdType.UNSURE, label=...)` with choices `[(AdType.SLIDE, f"Pre-show slide, ${AD_SLIDE_PRICE} a month"), (AdType.VIDEO, f"Video spot, ${AD_VIDEO_PRICE} a month"), (AdType.UNSURE, "Not sure yet")]`; `clean_ad_type()` returns `AdType.UNSURE` when empty. `message` is rebuilt as in the rentals form: `required=False, max_length=2000, Textarea(rows=4)`, error message "Please keep this under 2,000 characters."

- [ ] **Step 1: Write the failing tests**

```python
# web/tests/test_ad_inquiry_form.py
from cinema.models import AdType
from django.test import SimpleTestCase, TestCase
from web.constants import (
    AD_ARTWORK_DEADLINE_DAY, AD_SLIDE_PRICE, AD_VIDEO_MAX_SECONDS, AD_VIDEO_PRICE,
    ADVERTISING_FAQ,
)
from web.forms import AdInquiryForm


class AdvertisingConstantsTests(SimpleTestCase):
    def test_the_rates(self):
        self.assertEqual((AD_SLIDE_PRICE, AD_VIDEO_PRICE, AD_VIDEO_MAX_SECONDS, AD_ARTWORK_DEADLINE_DAY),
                         (75, 150, 30, 20))

    def test_faq_reads_from_the_constants(self):
        questions = [f["question"] for f in ADVERTISING_FAQ]
        self.assertEqual(questions, [
            "When does my ad start?", "How do I pay?", "Can I change my ad?",
            "What are the specs?", "Is there a contract?", "Do you run every ad?",
        ])
        answers = " ".join(f["answer"] for f in ADVERTISING_FAQ)
        self.assertIn("by the 20th", answers)
        self.assertIn("up to 30 seconds", answers)
        self.assertIn("political", answers)
        self.assertIn("Square invoice", answers)


class AdInquiryFormTests(TestCase):
    def data(self, **overrides):
        d = {"business_name": "Rock's Diner", "contact_name": "Pat", "email": "pat@example.com",
             "phone": "", "ad_type": "SLIDE", "message": "", "website": ""}
        d.update(overrides)
        return d

    def test_radio_labels_carry_the_prices(self):
        html = str(AdInquiryForm()["ad_type"])
        self.assertEqual(html.count('type="radio"'), 3)
        self.assertIn("Pre-show slide, $75 a month", html)
        self.assertIn("Video spot, $150 a month", html)
        self.assertIn("Not sure yet", html)

    def test_required_fields(self):
        form = AdInquiryForm(self.data(phone="", ad_type="", message=""))
        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual(form.cleaned_data["ad_type"], AdType.UNSURE)
        self.assertFalse(AdInquiryForm(self.data(business_name="")).is_valid())
        self.assertFalse(AdInquiryForm(self.data(contact_name="")).is_valid())
        self.assertFalse(AdInquiryForm(self.data(email="nope")).is_valid())

    def test_bogus_ad_type_is_rejected(self):
        form = AdInquiryForm(self.data(ad_type="BILLBOARD"))
        self.assertFalse(form.is_valid())
        self.assertIn("ad_type", form.errors)

    def test_message_is_capped(self):
        form = AdInquiryForm(self.data(message="x" * 2001))
        self.assertFalse(form.is_valid())
        self.assertIn("2,000 characters", form.errors["message"][0])

    def test_honeypot(self):
        self.assertTrue(AdInquiryForm(self.data(website="http://spam.example")).is_bot)
        self.assertFalse(AdInquiryForm(self.data()).is_bot)

    def test_labels(self):
        labels = {name: f.label for name, f in AdInquiryForm().fields.items()}
        self.assertEqual(labels["business_name"], "Business name")
        self.assertEqual(labels["contact_name"], "Your name")
        self.assertEqual(labels["phone"], "Phone (optional)")
        self.assertEqual(labels["ad_type"], "What are you interested in?")
        self.assertEqual(labels["message"], "Anything else? (optional)")
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `.venv/bin/python manage.py test web.tests.test_ad_inquiry_form -v 2`
Expected: FAIL with `ImportError` on `AD_ARTWORK_DEADLINE_DAY`

- [ ] **Step 3: Add the constants to `web/constants.py` after `RENTALS_FAQ`**

A short comment block in the file's style: the two rates and the terms, that `/advertise/` and its FAQPage markup both render `ADVERTISING_FAQ`, and that a term changes here and nowhere else. Build the answers with f-strings from the four numeric constants.

- [ ] **Step 4: Add `AdInquiryForm` to `web/forms.py` as specified in Interfaces**

Import `AdInquiry`, `AdType` from `cinema.models` and the two price constants from `web.constants`.

- [ ] **Step 5: Run the tests to verify they pass**

Run: `.venv/bin/python manage.py test web.tests.test_ad_inquiry_form -v 2`
Expected: 8 tests PASS

- [ ] **Step 6: Commit**

```bash
git add web/constants.py web/forms.py web/tests/test_ad_inquiry_form.py
git commit -m "feat(web): advertising rates, FAQ and inquiry form"
```

---

### Task 3: The `/advertise/` page, inquiry POST and stylesheet

**Files:**
- Create: `web/templates/web/advertise.html`
- Create: `templates/partials/ad_inquiry_form.html`
- Create: `static/css/AdvertisePage.css`
- Modify: `frontend/styles/main.css:53` (import after `PrivateRentalsPage.css`)
- Modify: `web/views.py` (imports around lines 24-36; new views after `RentalInquiryView`, line 348)
- Modify: `web/urls.py` (two paths after `rentals_inquire`)
- Test: `web/tests/test_advertise.py`, `web/tests/test_ad_inquiry.py`

**Interfaces:**
- Consumes: `AdInquiryForm` and the five constants from Task 2; `vote_engine.client_ip(request)` already imported in `web/views.py`.
- Produces: URL names `advertise` (`/advertise/`) and `advertise_inquire` (`/advertise/inquire`). `AdvertiseView(TemplateView)` with `template_name = "web/advertise.html"` and context keys `faqs`, `slide_price`, `video_price`, `video_max_seconds`, `artwork_deadline_day`, `form`, `sent`. `AdInquiryView(AdvertiseView)`: `get` redirects to `advertise`; `post` redirects bots and valid saves to `f"{reverse('advertise')}?sent=1#inquire"`, stores `ip`, and re-renders with the bound form on error. Same shape as `RentalsView` / `RentalInquiryView`.
- Page copy the tests pin: `<title>` "Advertise on the Big Screen | Fort Kent Cinema"; `<h1>` "YOUR BUSINESS ON THE BIG SCREEN"; subtitle "A room full of neighbors, every show, from the moment the doors open."; section titles "THE RATES", "HOW IT WORKS", "QUESTIONS WE GET", "READY TO GET STARTED?"; card titles "PRE-SHOW SLIDE" and "VIDEO SPOT"; the three steps "Send us the form below.", "We confirm your spot and invoice you through Square each month.", "Get us your artwork by the 20th and you're on screen the 1st."; the sent box "Thanks — we've got it." and "We'll be in touch within a few days."; "Or call" with the phone link, as on rentals. Meta description: "Put your business in front of a room full of neighbors before every show at Fort Kent Cinema. Pre-show slides from $75 a month, video spots from $150." OG image `img/involved/your-ad-here.jpg`, `og_image_details` overridden to width 1200, height 675, alt "A 'Your ad here' slide on the Fort Kent Cinema screen".

- [ ] **Step 1: Write the failing page tests**

```python
# web/tests/test_advertise.py
import json
import re

from django.test import TestCase
from django.urls import reverse
from web.constants import ADVERTISING_FAQ


class AdvertisePageTests(TestCase):
    def setUp(self):
        self.response = self.client.get(reverse("advertise"))
        self.html = self.response.content.decode()

    def test_renders(self):
        self.assertEqual(self.response.status_code, 200)
        self.assertTemplateUsed(self.response, "web/advertise.html")
        self.assertIn("<title>Advertise on the Big Screen | Fort Kent Cinema</title>", self.html)
        self.assertIn("YOUR BUSINESS ON THE BIG SCREEN", self.html)

    def test_the_two_rates(self):
        for text in ("PRE-SHOW SLIDE", "VIDEO SPOT", "$75", "$150", "30 seconds",
                     "1920", "PNG or JPEG", "MP4", "THE RATES", "HOW IT WORKS"):
            self.assertIn(text, self.html, text)
        # Nothing promises a count.
        self.assertNotRegex(self.html, r"\d[\d,]* (people|views|plays)")

    def test_exposure_promise(self):
        self.assertIn("before every show", self.html)
        self.assertIn("30 minutes before showtime", self.html)

    def test_how_it_works_names_the_deadline_and_square(self):
        self.assertIn("by the 20th", self.html)
        self.assertIn("invoice you through Square", self.html)

    def test_faq_renders_once_visibly_and_once_as_json_ld(self):
        for faq in ADVERTISING_FAQ:
            self.assertEqual(self.html.count(faq["question"]), 2, faq["question"])
        block = re.search(r'<script type="application/ld\+json">\s*(\{.*?\})\s*</script>',
                          self.html, re.S).group(1)
        data = json.loads(block)
        self.assertEqual(data["@type"], "FAQPage")
        self.assertEqual([q["name"] for q in data["mainEntity"]],
                         [f["question"] for f in ADVERTISING_FAQ])

    def test_policy_is_on_the_page(self):
        self.assertIn("political", self.html)
        self.assertIn("decline any ad", self.html)

    def test_form_is_on_the_page(self):
        self.assertIn('id="inquire"', self.html)
        self.assertIn(f'action="{reverse("advertise_inquire")}"', self.html)
        self.assertIn('name="business_name"', self.html)
        self.assertIn('name="email"', self.html)
        self.assertEqual(self.html.count('name="ad_type"'), 3)
        self.assertIn("Pre-show slide, $75 a month", self.html)
        # Radios sit in a fieldset, not nested inside another <label>.
        self.assertIn("<fieldset", self.html)
        self.assertNotRegex(self.html, r"<label[^>]*>\s*<span[^>]*>What are you interested in\?")

    def test_og_image_is_the_card_art(self):
        self.assertRegex(self.html, r'<meta property="og:image" content="[^"]*img/involved/your-ad-here\.jpg" />')
        self.assertIn('<meta property="og:image:width" content="1200" />', self.html)
        self.assertIn('<meta property="og:image:height" content="675" />', self.html)
        self.assertRegex(self.html, r'<meta property="og:image:alt" content="[^"]{10,}" />')

    def test_phone_fallback(self):
        self.assertIn("Or call", self.html)
        self.assertIn('data-track="phone_click" data-track-location="advertise"', self.html)
```

- [ ] **Step 2: Write the failing inquiry tests**

```python
# web/tests/test_ad_inquiry.py
from cinema.models import AdInquiry, AdType, InquiryStatus
from django.test import TestCase
from django.urls import reverse


class AdInquiryTests(TestCase):
    def payload(self, **overrides) -> dict:
        data = {"business_name": "Rock's Diner", "contact_name": "Pat Harper",
                "email": "pat@example.com", "phone": "(207) 555-0100",
                "ad_type": "VIDEO", "message": "We'd like to start in December.",
                "website": ""}
        data.update(overrides)
        return data

    def test_valid_post_creates_an_inquiry(self):
        response = self.client.post(reverse("advertise_inquire"), self.payload())
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response["Location"], f"{reverse('advertise')}?sent=1#inquire")
        row = AdInquiry.objects.get()
        self.assertEqual(row.business_name, "Rock's Diner")
        self.assertEqual(row.contact_name, "Pat Harper")
        self.assertEqual(row.ad_type, AdType.VIDEO)
        self.assertEqual(row.status, InquiryStatus.NEW)

    def test_omitted_ad_type_defaults_to_unsure(self):
        data = self.payload()
        del data["ad_type"]
        self.client.post(reverse("advertise_inquire"), data)
        self.assertEqual(AdInquiry.objects.get().ad_type, AdType.UNSURE)

    def test_bogus_ad_type_is_rejected(self):
        response = self.client.post(reverse("advertise_inquire"), self.payload(ad_type="BILLBOARD"))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(AdInquiry.objects.count(), 0)

    def test_blank_business_name_is_rejected(self):
        response = self.client.post(reverse("advertise_inquire"), self.payload(business_name="   "))
        self.assertEqual(AdInquiry.objects.count(), 0)
        self.assertContains(response, "This field is required")

    def test_invalid_email_is_rejected(self):
        response = self.client.post(reverse("advertise_inquire"), self.payload(email="not-an-email"))
        self.assertEqual(AdInquiry.objects.count(), 0)
        self.assertContains(response, "valid email")

    def test_overlength_message_is_rejected(self):
        response = self.client.post(reverse("advertise_inquire"), self.payload(message="x" * 2001))
        self.assertEqual(AdInquiry.objects.count(), 0)
        self.assertContains(response, "2,000 characters")

    def test_error_response_is_the_full_page(self):
        response = self.client.post(reverse("advertise_inquire"), self.payload(email="nope"))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "web/advertise.html")
        self.assertContains(response, "QUESTIONS WE GET")
        self.assertContains(response, "Rock&#x27;s Diner")  # values survive

    def test_success_message_is_shown_after_the_redirect(self):
        html = self.client.get(reverse("advertise"), {"sent": "1"}).content.decode()
        self.assertIn("Thanks", html)
        self.assertNotIn('name="business_name"', html)

    def test_honeypot_silently_succeeds_without_a_row(self):
        response = self.client.post(reverse("advertise_inquire"),
                                    self.payload(website="http://spam.example"))
        self.assertEqual(response.status_code, 302)
        self.assertIn("sent=1", response["Location"])
        self.assertEqual(AdInquiry.objects.count(), 0)

    def test_client_ip_is_recorded(self):
        self.client.post(reverse("advertise_inquire"), self.payload(), REMOTE_ADDR="203.0.113.9")
        self.assertEqual(AdInquiry.objects.get().ip, "203.0.113.9")

    def test_malformed_forwarded_header_does_not_500(self):
        response = self.client.post(reverse("advertise_inquire"), self.payload(),
                                    HTTP_X_FORWARDED_FOR="not-an-ip")
        self.assertEqual(response.status_code, 302)
        self.assertIsNone(AdInquiry.objects.get().ip)

    def test_get_redirects_to_the_page(self):
        self.assertRedirects(self.client.get(reverse("advertise_inquire")), reverse("advertise"))
```

- [ ] **Step 3: Run both files to verify they fail**

Run: `.venv/bin/python manage.py test web.tests.test_advertise web.tests.test_ad_inquiry -v 2`
Expected: every test FAILS with `NoReverseMatch: Reverse for 'advertise' not found`

- [ ] **Step 4: Add the views to `web/views.py` and the URLs to `web/urls.py`**

Import `AdInquiryForm` and the five advertising constants. `AdvertiseView` and `AdInquiryView` as in Interfaces, with docstrings matching the rentals pair. URL lines: `path("advertise/", AdvertiseView.as_view(), name="advertise")` and `path("advertise/inquire", AdInquiryView.as_view(), name="advertise_inquire")`.

- [ ] **Step 5: Write `templates/partials/ad_inquiry_form.html`**

Copy `rental_inquiry_form.html` with the `rental-inquire__` classes renamed `ad-inquire__`, action `{% url 'advertise_inquire' %}`, button text "Send it over" with `data-track="ad_inquiry_submit"`, and the sent copy from Interfaces (keep the "If it's urgent, call {{ site_config.cinema.phone }}." line). In the `visible_fields` loop, render `ad_type` differently: `{% if field.name == "ad_type" %}<fieldset class="ad-inquire__choices"><legend class="ad-inquire__label">{{ field.label }}</legend>{{ field }}{% if field.errors %}<span class="ad-inquire__field-error">{{ field.errors|join:" " }}</span>{% endif %}</fieldset>{% else %}` …the existing `<label>` block… `{% endif %}`.

- [ ] **Step 6: Write `web/templates/web/advertise.html`**

Structure of `rentals.html` with the `rentals-`/`rental-` class prefixes renamed `advertise-`/`ad-card`: head blocks and the FAQPage JSON-LD loop verbatim from rentals but over this page's `faqs`; the `og_image`, `og_image_details` (width 1200, height 675, alt) overrides; header; "THE RATES" section with a note "Both run in the loop before every show, from the time the doors open, 30 minutes before showtime." and two cards (`ad-card`, the video one `ad-card--featured`), prices as `${{ slide_price }}` and `${{ video_price }}` with `<span>per month</span>`, features from the spec (slide: "Plays before every show", "1920 × 1080 PNG or JPEG, supplied by you", "Swap it any month", "No contract"; video: "Plays before every show", "Up to {{ video_max_seconds }} seconds", "MP4, 1920 × 1080, supplied by you", "Swap it any month", "No contract"); "HOW IT WORKS" as an `<ol class="advertise-steps">` with the three steps, the deadline written `{{ artwork_deadline_day }}th`; the FAQ `<dl>` as on rentals; the `id="inquire"` section titled "READY TO GET STARTED?" with text "Tell us a little about your business and we'll get back to you to confirm your spot.", the partial, and the "Or call" line with `data-track-location="advertise"`.

- [ ] **Step 7: Write `static/css/AdvertisePage.css` and import it**

Copy `PrivateRentalsPage.css` with the renamed prefixes, plus rules for `.advertise-steps` (numbered list, same type sizes as the FAQ) and `.ad-inquire__choices` (no border, zero padding, legend styled as `.ad-inquire__label`, each radio row `display: flex; gap: .5rem; align-items: center` with the input `width: auto`). Add `@import '../../static/css/AdvertisePage.css';` after the rentals line in `frontend/styles/main.css`.

- [ ] **Step 8: Rebuild the bundle and run the tests**

Run: `(cd frontend && npm run build:css) && .venv/bin/python manage.py test web.tests.test_advertise web.tests.test_ad_inquiry web.tests.test_rental_inquiry -v 2`
Expected: all PASS, rentals included.

- [ ] **Step 9: Look at it**

Run the dev server and open `/advertise/`, `/advertise/?sent=1#inquire`, and submit a blank form, at desktop and 390px width. The cards sit side by side on desktop and stack on phone; the radios read as one group; nothing overflows horizontally.

- [ ] **Step 10: Commit**

```bash
git add web/templates/web/advertise.html templates/partials/ad_inquiry_form.html static/css/AdvertisePage.css static/css/bundle.css frontend/styles/main.css web/views.py web/urls.py web/tests/test_advertise.py web/tests/test_ad_inquiry.py
git commit -m "feat(web): /advertise/ page with rates, FAQ and inquiry form"
```

---

### Task 4: Dashboard list, status change, sidebar and smart alert

**Files:**
- Create: `dashboard/ad_inquiry_views.py`
- Create: `dashboard/templates/dashboard/ad_inquiries.html`
- Modify: `dashboard/urls.py:286-295` (two routes after the rental ones; import the module at the top)
- Modify: `dashboard/templates/dashboard/_sidebar.html:20-21` (entry after Rental Inquiries)
- Modify: `dashboard/smart_alerts.py:8-14,50-55`
- Modify: `dashboard/views.py:15,95-97` (import and count)
- Test: `dashboard/tests/test_ad_inquiries.py`, `dashboard/tests/test_smart_alerts.py`

**Interfaces:**
- Consumes: `AdInquiry`, `InquiryStatus` from Task 1.
- Produces: URL names `dashboard:ad_inquiries` (`ad-inquiries`) and `dashboard:ad_inquiry_status` (`ad-inquiries/<int:pk>/status`). `AdInquiryListView(StaffRequiredMixin, View)` renders `dashboard/ad_inquiries.html` with context `inquiries`, `new_count`, `statuses`, `selected_status`, filtering on `?status=`. `AdInquiryStatusView(StaffRequiredMixin, View).post(request, pk)` sets a valid status and redirects to the list. `build_smart_alerts(..., new_ad_inquiries: int = 0, ...)` appends `{"id": "new-ad-inquiries", "type": "info", "message": "You have N new ad inquiry|inquiries", "url": reverse("dashboard:ad_inquiries")}` when N > 0, placed right after the rental alert.

- [ ] **Step 1: Write the failing dashboard tests**

```python
# dashboard/tests/test_ad_inquiries.py
from cinema.models import AdInquiry, AdType, InquiryStatus
from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse


class AdInquiryListTests(TestCase):
    def setUp(self):
        self.staff = get_user_model().objects.create_user(username="staff", password="pw", is_staff=True)
        self.inquiry = AdInquiry.objects.create(
            business_name="Rock's Diner", contact_name="Pat Harper", email="pat@example.com",
            phone="(207) 555-0100", ad_type=AdType.VIDEO, message="December start?",
        )

    def test_requires_staff(self):
        self.assertNotEqual(self.client.get(reverse("dashboard:ad_inquiries")).status_code, 200)

    def test_lists_inquiries(self):
        self.client.force_login(self.staff)
        response = self.client.get(reverse("dashboard:ad_inquiries"))
        self.assertEqual(response.status_code, 200)
        for text in ("Rock&#x27;s Diner", "Pat Harper", "pat@example.com", "Video spot", "December start?"):
            self.assertContains(response, text)
        self.assertEqual(response.context["new_count"], 1)

    def test_message_is_escaped(self):
        self.inquiry.message = "<script>alert(1)</script>"
        self.inquiry.save()
        self.client.force_login(self.staff)
        response = self.client.get(reverse("dashboard:ad_inquiries"))
        self.assertNotContains(response, "<script>alert(1)</script>")
        self.assertContains(response, "&lt;script&gt;")

    def test_filter_by_status(self):
        AdInquiry.objects.create(business_name="Won Co", contact_name="w", email="w@example.com",
                                 status=InquiryStatus.WON)
        self.client.force_login(self.staff)
        response = self.client.get(reverse("dashboard:ad_inquiries"), {"status": "WON"})
        self.assertContains(response, "Won Co")
        self.assertNotContains(response, "Pat Harper")

    def test_status_can_be_changed(self):
        self.client.force_login(self.staff)
        response = self.client.post(reverse("dashboard:ad_inquiry_status", args=[self.inquiry.pk]),
                                    {"status": "CONTACTED"})
        self.assertRedirects(response, reverse("dashboard:ad_inquiries"))
        self.inquiry.refresh_from_db()
        self.assertEqual(self.inquiry.status, InquiryStatus.CONTACTED)

    def test_invalid_status_is_ignored(self):
        self.client.force_login(self.staff)
        self.client.post(reverse("dashboard:ad_inquiry_status", args=[self.inquiry.pk]), {"status": "BOGUS"})
        self.inquiry.refresh_from_db()
        self.assertEqual(self.inquiry.status, InquiryStatus.NEW)

    def test_status_change_requires_staff(self):
        self.client.post(reverse("dashboard:ad_inquiry_status", args=[self.inquiry.pk]), {"status": "CONTACTED"})
        self.inquiry.refresh_from_db()
        self.assertEqual(self.inquiry.status, InquiryStatus.NEW)

    def test_sidebar_links_to_ad_inquiries(self):
        self.client.force_login(self.staff)
        html = self.client.get(reverse("dashboard:home")).content.decode()
        self.assertIn(reverse("dashboard:ad_inquiries"), html)
        self.assertIn("Ad Inquiries", html)

    def test_home_alert_counts_new_ad_inquiries(self):
        AdInquiry.objects.create(business_name="Done", contact_name="d", email="d@example.com",
                                 status=InquiryStatus.LOST)
        self.client.force_login(self.staff)
        response = self.client.get(reverse("dashboard:home"))
        self.assertContains(response, "You have 1 new ad inquiry")
```

And append to `dashboard/tests/test_smart_alerts.py`:

```python
class AdInquiryAlertTests(TestCase):
    def setUp(self) -> None:
        self.today = datetime.date(2026, 7, 10)

    def _alert(self, count: int) -> dict | None:
        alerts = build_smart_alerts([], 1, self.today, new_ad_inquiries=count)
        return next((a for a in alerts if a["id"] == "new-ad-inquiries"), None)

    def test_zero_is_silent(self):
        self.assertIsNone(self._alert(0))

    def test_singular_and_plural(self):
        self.assertEqual(self._alert(1)["message"], "You have 1 new ad inquiry")
        self.assertEqual(self._alert(2)["message"], "You have 2 new ad inquiries")

    def test_links_to_the_list(self):
        self.assertEqual(self._alert(1)["url"], reverse("dashboard:ad_inquiries"))
```

(add `from django.urls import reverse` to that file's imports if absent.)

- [ ] **Step 2: Run them to verify they fail**

Run: `.venv/bin/python manage.py test dashboard.tests.test_ad_inquiries dashboard.tests.test_smart_alerts -v 2`
Expected: `NoReverseMatch` for `dashboard:ad_inquiries`; `TypeError` on `new_ad_inquiries`.

- [ ] **Step 3: Create `dashboard/ad_inquiry_views.py`**

Copy `rental_inquiry_views.py` with `AdInquiry`, the new template name, and `redirect("dashboard:ad_inquiries")`.

- [ ] **Step 4: Create `dashboard/templates/dashboard/ad_inquiries.html`**

Copy `rental_inquiries.html`. Title and heading "Ad Inquiries". Columns: Business | Contact (name, mailto, phone) | Ad type (`{{ inquiry.get_ad_type_display }}`) | Received | Status. Message row `colspan="5"`. Empty state "No Ad Inquiries Yet" / "They'll show up here when someone fills in the form on /advertise/."

- [ ] **Step 5: Wire the routes and the sidebar**

In `dashboard/urls.py` import `ad_inquiry_views` and add the two paths after the rental ones. In `_sidebar.html`, after the Rental Inquiries anchor, the same anchor shape for `dashboard:ad_inquiries` labelled "Ad Inquiries" with a megaphone: `<path d="M3 8v4h3l6 4V4L6 8H3z" stroke="currentColor" stroke-width="1.5" stroke-linejoin="round"/><path d="M14.5 7.5a3.5 3.5 0 010 5" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"/>`.

- [ ] **Step 6: Add the alert and the count**

`smart_alerts.py`: the `new_ad_inquiries: int = 0` parameter after `new_rental_inquiries`, and the alert block after the rental one, per Interfaces. `dashboard/views.py`: import `AdInquiry` and pass `new_ad_inquiries=AdInquiry.objects.filter(status=InquiryStatus.NEW).count()`.

- [ ] **Step 7: Run the tests**

Run: `.venv/bin/python manage.py test dashboard -v 2`
Expected: all PASS

- [ ] **Step 8: Commit**

```bash
git add dashboard/ad_inquiry_views.py dashboard/templates/dashboard/ad_inquiries.html dashboard/urls.py dashboard/templates/dashboard/_sidebar.html dashboard/smart_alerts.py dashboard/views.py dashboard/tests/test_ad_inquiries.py dashboard/tests/test_smart_alerts.py
git commit -m "feat(dashboard): ad inquiries list, status and alert"
```

---

### Task 5: Home card link, footer, sitemap, llms.txt, and final verification

**Files:**
- Modify: `templates/partials/cta_advertise.html` (comment and a `home-link`)
- Modify: `web/constants.py:53-80` (`footer_navigation`, first item)
- Modify: `web/sitemaps.py:22-31,38-48`
- Modify: `templates/llms.txt:44-46`
- Modify: `web/tests/test_home_sections.py:479-486`, `web/tests/test_nav.py:76-96`, `web/tests/test_sitemap_lastmod.py:50-54`, `web/tests/test_llms_txt.py`

**Interfaces:**
- Consumes: URL name `advertise` from Task 3.
- Produces: nothing downstream.

- [ ] **Step 1: Edit the tests first**

In `test_home_sections.py`, replace `test_advertise_card_is_third_and_has_no_link_yet` with:

```python
    def test_advertise_card_links_to_the_page(self):
        # Added 2026-10-13 without a link; /advertise/ landed 2026-10-14.
        section = self.section()
        self.assertLess(section.index("heckle-night-cta"), section.index("advertise-cta"))
        card = self.card("advertise-cta")
        self.assertIn("Advertise with us", card)
        self.assertIn(f'<a href="{reverse("advertise")}" class="home-link">See rates &rarr;</a>', card)
```

In `test_nav.py`, make `test_footer_holds_what_left_more` expect `["Advertise", "Century Theatre in Fort Kent", "From the Booth", "Private Rentals", "You Choose"]` and add:

```python
    def test_advertise_link_lives_in_the_footer(self):
        item = footer_item("/advertise/")
        self.assertEqual(item["label"], "Advertise")
        self.assertEqual(item["note"], "Your business on the big screen")
        html = footer_html(self.client.get("/").content.decode())
        self.assertIn('href="/advertise/"', html)
```

In `test_sitemap_lastmod.py`, extend `test_the_sitemap_actually_emits_them` to loop over `("/rentals/", "/advertise/")` with the same two assertions per path.

In `test_llms_txt.py`, add (same decorators as its neighbours):

```python
    def test_advertising_is_listed(self, *_):
        text = self.get().content.decode()
        self.assertIn("## Rentals, advertising", text)
        self.assertIn("http://testserver/advertise/", text)
```

- [ ] **Step 2: Run them to verify they fail**

Run: `.venv/bin/python manage.py test web.tests.test_home_sections web.tests.test_nav web.tests.test_sitemap_lastmod web.tests.test_llms_txt -v 2`
Expected: the four new or changed tests FAIL; everything else passes.

- [ ] **Step 3: Make the edits**

- `cta_advertise.html`: replace the "No link yet" comment with one line saying the page is `/advertise/`, and add `<a href="{% url 'advertise' %}" class="home-link">See rates &rarr;</a>` after the body paragraph.
- `web/constants.py`: insert `{"label": "Advertise", "note": "Your business on the big screen", "href": "/advertise/"}` as the first `footer_navigation` item.
- `web/sitemaps.py`: `"advertise": datetime.date(2026, 10, 14)` in `STATIC_PAGE_LASTMOD` and `"advertise"` in `items()` after `"rentals"`.
- `templates/llms.txt`: heading `## Rentals, advertising` and a second bullet `- Advertising on the big screen before every show: {{ base }}/advertise/`.

- [ ] **Step 4: Run the four files again**

Run: `.venv/bin/python manage.py test web.tests.test_home_sections web.tests.test_nav web.tests.test_sitemap_lastmod web.tests.test_llms_txt web.tests.test_sitemap -v 2`
Expected: all PASS

- [ ] **Step 5: Full suite, migration check, and lint on changed lines**

Run: `.venv/bin/python manage.py test && .venv/bin/python manage.py makemigrations --check --dry-run && git diff main --name-only | grep '\.py$' | xargs .venv/bin/flake8`
Expected: suite green; "No changes detected"; flake8 reports nothing on the new files and nothing new on edited lines (compare any hit against `git diff main` to confirm it predates this branch).

- [ ] **Step 6: Screenshot pass**

With the dev server up, capture `/advertise/` at desktop and 390px, `/advertise/?sent=1#inquire`, the page after an empty submit, the home card with its new link, the footer, and the dashboard list with one NEW row. Save under the scratchpad directory and check each by eye.

- [ ] **Step 7: Commit**

```bash
git add templates/partials/cta_advertise.html web/constants.py web/sitemaps.py templates/llms.txt web/tests/test_home_sections.py web/tests/test_nav.py web/tests/test_sitemap_lastmod.py web/tests/test_llms_txt.py
git commit -m "feat(home): link the Advertise card, footer, sitemap and llms.txt to /advertise/"
```

Stop here. Merge and push only when asked.
