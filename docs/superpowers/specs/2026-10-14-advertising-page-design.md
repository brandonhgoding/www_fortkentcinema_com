# Advertising page — design

Date: 2026-10-14
Status: approved in conversation; awaiting review of this written spec

## Goal

A public `/advertise/` page that sells pre-show screen advertising to local
businesses and takes an inquiry through a form, with the inquiry landing in
the dashboard the way rental inquiries do. The home page's "Advertise with
us" card (added 2026-10-13 without a link) gets its link.

## Decisions (the owner's, via the developer)

| Question | Decision |
|---|---|
| What the visitor does | Sends an inquiry form; no self-serve purchase, no email |
| Products | Two, billed monthly: a static pre-show slide and a short video spot |
| Prices | Slide $75 a month. Video spot, up to 30 seconds, $150 a month |
| Discounts or terms | None. Month to month, no contract |
| Artwork | The business supplies it to spec. The theater does not design |
| Months | Calendar months. Artwork due by the 20th, on screen the 1st |
| Payment | The theater sends a Square invoice each month |
| Content policy | The theater reserves the right to refuse any ad. No political ads |
| Exposure promise | "Before every show, from when doors open 30 minutes before showtime." No counts, no reach figure |
| Structure | A sibling of rentals: its own model, form, dashboard list, alert. Rentals untouched |

## Pricing research (for the record)

Published rate cards at small-town independents, October 2026:

| Theater | Town, approx. population | Slide / month | Video / month |
|---|---|---|---|
| Paradise Theatre, Mora MN | 3,500, nonprofit | about $30 | not separate |
| Mariner Theatre, Marinette WI | 10,000 | $50 per 15 s | same |
| Silco Theater, Silver City NM | 9,000 | $75 | $100 (30 s), $200 (60 s) |
| Webster Theater, Webster City IA | 7,500 | $150 (:15) | $187 (:30) |
| Bellows Falls Opera House VT | 3,000 | $150, nonprofit $100 | by inquiry |
| Crandell Theatre, Chatham NY | 4,000 | $150 | not offered |
| Co-Ed Cinema, Brevard NC | 8,000 | $150, nonprofit $100 | $300 (60 s) |

$75 / $150 sits above the nonprofit floor and under the arts-town rate.
Video at roughly twice the slide price matches every theater that offers it.

## Assumptions

- No mail is sent. The database row is the notification, as with rentals.
- The existing `static/img/involved/your-ad-here.jpg` serves as the page's
  social image. No new artwork.
- Spec for supplied artwork: 1920 × 1080 PNG or JPEG for a slide; MP4,
  1920 × 1080, up to 30 seconds, for video.
- The `footer_navigation` list in `SITE_CONFIG` is alphabetical by label, so
  "Advertise" becomes its first item.

## Section 1 — The public page

### URLs and wiring

- `path("advertise/", AdvertiseView.as_view(), name="advertise")`
- `path("advertise/inquire", AdInquiryView.as_view(), name="advertise_inquire")`
- `templates/partials/cta_advertise.html` gains
  `<a href="{% url 'advertise' %}" class="home-link">See rates &rarr;</a>`
  at the bottom, like `cta_openmic.html`. Its "no link yet" comment goes.
- `SITE_CONFIG["footer_navigation"]` gains
  `{"label": "Advertise", "note": "Your business on the big screen", "href": "/advertise/"}`,
  first in the alphabetical list.
- `web/sitemaps.py`: an `advertise` entry with lastmod 2026-10-14 and the
  name in the static list.
- `templates/llms.txt`: under the "Rentals, gift cards" heading, a line
  `- Advertising on the big screen before every show: {{ base }}/advertise/`.
  The heading becomes "Rentals, advertising, gift cards".

### Head

- Title: `Advertise on the Big Screen | Fort Kent Cinema`.
- Description: "Put your business in front of a room full of neighbors
  before every show at Fort Kent Cinema. Pre-show slides from $75 a month,
  video spots from $150."
- `og_title`, `og_description` to match; `og_image` overrides to
  `img/involved/your-ad-here.jpg` with a matching `og_image_alt`.
- A `FAQPage` JSON-LD block rendered from `ADVERTISING_FAQ`, the same loop
  the rentals template uses, so the markup never drifts from the visible FAQ.

### Layout (`web/templates/web/advertise.html`)

Mirrors `rentals.html` top to bottom.

1. **Header.** Back link, `<h1>` "YOUR BUSINESS ON THE BIG SCREEN", subtitle
   "A room full of neighbors, every show, from the moment the doors open."
2. **Rates.** Section title "THE RATES", one-line note that both run before
   every show from the time doors open, 30 minutes before showtime. Two
   cards side by side:
   - **PRE-SHOW SLIDE**, `$75` per month. One still image in the loop before
     every show. Features: plays before every show; 1920 × 1080 PNG or JPEG,
     supplied by you; swap it any month; no contract.
   - **VIDEO SPOT**, `$150` per month. Up to 30 seconds, before every show.
     Features: plays before every show; up to 30 seconds; MP4, 1920 × 1080,
     supplied by you; swap it any month; no contract.
   Prices and the second cap render from constants, never typed in the
   template.
3. **How it works.** Three numbered steps: "Send us the form below." "We
   confirm your spot and invoice you through Square each month." "Get us your
   artwork by the 20th and you're on screen the 1st."
4. **FAQ.** From `ADVERTISING_FAQ`:
   - *When does my ad start?* Ads run by calendar month. Send artwork by the
     20th and it plays from the 1st of the next month.
   - *How do I pay?* We send a Square invoice each month. Pay online by card
     or at the box office.
   - *Can I change my ad?* Yes. Send new artwork by the 20th and it swaps on
     the 1st.
   - *What are the specs?* Slides: 1920 × 1080 PNG or JPEG. Video: MP4,
     1920 × 1080, up to 30 seconds. We'll check it and send a proof.
   - *Is there a contract?* No. Month to month; stop whenever you like.
   - *Do you run every ad?* We reserve the right to decline any ad, and we
     don't run political ads.
5. **Form.** Section title "READY TO GET STARTED?", anchored `#inquire`, the
   form partial, and the `sent` confirmation ("Thanks — we'll be in touch
   within a few days.") when `?sent=1`.

### CSS

- New `static/css/AdvertisePage.css`, imported in `frontend/styles/main.css`
  after `PrivateRentalsPage.css`. Class prefix `advertise-` for the page and
  `ad-inquire__` for the form, copying the rentals and rental-form rules so
  the two pages read as siblings. The bundle is rebuilt.

## Section 2 — Data and form

### Model (`cinema/models/ad_inquiry.py`)

```python
class AdType(models.TextChoices):
    SLIDE = "SLIDE", "Pre-show slide"
    VIDEO = "VIDEO", "Video spot"
    UNSURE = "UNSURE", "Not sure yet"

class AdInquiry(models.Model):
    business_name = CharField(max_length=200)
    contact_name = CharField(max_length=200)
    email = EmailField()
    phone = CharField(max_length=40, blank=True)
    ad_type = CharField(max_length=10, choices=AdType.choices, default=AdType.UNSURE)
    message = TextField(blank=True)
    status = CharField(max_length=20, choices=InquiryStatus.choices, default=InquiryStatus.NEW)
    created_at = DateTimeField(auto_now_add=True)
    ip = GenericIPAddressField(null=True, blank=True)
    # Meta: ordering ["-created_at"], verbose_name_plural "Ad inquiries"
```

`InquiryStatus` is imported from `rental_inquiry.py`; `AdInquiry` and
`AdType` are exported from `cinema/models/__init__.py`. One migration,
`cinema/migrations/0028_adinquiry.py`, containing only this model.

### Constants (`web/constants.py`)

- `AD_SLIDE_PRICE = 75`
- `AD_VIDEO_PRICE = 150`
- `AD_VIDEO_MAX_SECONDS = 30`
- `AD_ARTWORK_DEADLINE_DAY = 20`
- `ADVERTISING_FAQ`, the list in Section 1, with the numbers interpolated
  from the constants above.

### Form (`web/forms.py`)

`AdInquiryForm(forms.ModelForm)` with the same `website` honeypot and
`is_bot` property as `RentalInquiryForm`. Fields: `business_name`,
`contact_name`, `email`, `phone`, `ad_type`, `message`. Labels: "Business
name", "Your name", "Email", "Phone (optional)", "What are you interested
in?", "Anything else? (optional)". `ad_type` renders as a `RadioSelect`
whose labels carry the prices, built from the constants: "Pre-show slide,
$75 a month", "Video spot, $150 a month", "Not sure yet".

### Views (`web/views.py`)

- `AdvertiseView(TemplateView)`: context `faqs`, `slide_price`,
  `video_price`, `video_max_seconds`, `artwork_deadline_day`, `form`
  (bound form from kwargs or a fresh one), `sent`.
- `AdInquiryView(AdvertiseView)`: `get` redirects to `advertise`; `post`
  redirects bots and valid submissions to `reverse("advertise") + "?sent=1#inquire"`,
  sets `inquiry.ip = vote_engine.client_ip(request)` on save, and re-renders
  the page with the bound form on validation error. Same shape as
  `RentalInquiryView`.

## Section 3 — Dashboard

- `dashboard/ad_inquiry_views.py`: `AdInquiryListView` (status filter, NEW
  count, `statuses`, `selected_status`) and `AdInquiryStatusView` (POST
  status change, redirect to the list). Both `StaffRequiredMixin`.
- Routes in `dashboard/urls.py`: `ad-inquiries` → `ad_inquiries`,
  `ad-inquiries/<int:pk>/status` → `ad_inquiry_status`.
- `dashboard/templates/dashboard/ad_inquiries.html`, copied from
  `rental_inquiries.html` with columns: business, contact, email, phone, ad
  type, message, received, status.
- `_sidebar.html`: "Ad Inquiries" directly under "Rental Inquiries", with a
  megaphone inline SVG in the same style.
- `smart_alerts.py`: new keyword argument `new_ad_inquiries: int = 0` and an
  info alert `{"id": "new-ad-inquiries", "message": "You have N new ad
  inquiry/inquiries", ...}` linking to the list. `dashboard/views.py` passes
  `AdInquiry.objects.filter(status=NEW).count()`.
- `cinema/admin.py`: a plain `ModelAdmin` with list display (business,
  contact, ad type, status, created) and a status filter.

## Section 4 — Testing and delivery

Tests are written first.

### New test files

- `web/tests/test_advertise.py`: 200; both prices and the 30-second cap on
  the page; the FAQ appears once visibly and once as `FAQPage` JSON-LD from
  the same list; the three ad-type radios carry prices in their labels; the
  refusal and no-political-ads answer is present; the OG image is
  `your-ad-here.jpg`.
- `web/tests/test_ad_inquiry.py`: valid POST saves a row with `ip` and
  redirects to `?sent=1#inquire`; bot POST saves nothing and redirects the
  same way; missing business or email re-renders with errors and saves
  nothing; GET on the inquire URL redirects to the page; `ad_type` defaults
  to UNSURE when omitted.
- `dashboard/tests/test_ad_inquiries.py`: anonymous users are redirected;
  the list shows rows and filters by status; the status POST updates the
  row; the sidebar links to the list.

### Edited tests

- `web/tests/test_home_sections.py`: `test_advertise_card_is_third_and_has_no_link_yet`
  becomes `test_advertise_card_links_to_the_page`, asserting the `home-link`
  to `/advertise/`.
- `web/tests/test_nav.py`: a footer test for `/advertise/` with its note,
  and it is the first Explore item.
- `web/tests/test_sitemap_lastmod.py` and `test_sitemap.py`: the page has a
  lastmod and is in the sitemap.
- `web/tests/test_llms_txt.py`: the advertise line and renamed heading.
- `dashboard/tests/test_smart_alerts.py`: the ad alert appears for a
  positive count, singular and plural, and not for zero.

### Verification

- Full suite green. `makemigrations --check` clean. CSS bundle rebuilt.
- flake8: no new findings on changed lines (the repo baseline is dirty).
- Screenshots of `/advertise/` at desktop and phone width, the sent state,
  a validation error, and the dashboard list with one NEW row.

### Delivery

- Branch `feat/advertise-page`. Ordered commits: constants, page and CSS;
  model, migration and form; dashboard and alert; home card link, footer,
  sitemap, llms.txt. Suite passes after each.
- Commit, merge and push only when the developer asks. The owner deploys.

## Out of scope

Self-serve purchase, multi-month discounts, a reach figure, design services,
email notifications, and any change to the rentals flow.
