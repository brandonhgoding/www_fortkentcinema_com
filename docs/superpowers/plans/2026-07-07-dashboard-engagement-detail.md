# Dashboard EngagementDetail Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** The per-engagement detail page at `/dashboard/engagements/<id>` — read-only info panel plus full showtimes management (list, single create/edit/delete, bulk add across a date range), with runtime-aware overlap validation.

**Architecture:** A ported overlap service in `cinema/` validates single + bulk showtime creation; class-based `dashboard` views render fragments; showtime mutations OOB-refresh the `#showtime-list` region; the bulk form uses an Alpine array of time slots. Date+time combine into an aware `starts_at` in America/New_York.

**Tech Stack:** Django 5.2 (USE_TZ, TIME_ZONE=America/New_York), HTMX + Alpine, Django `TestCase`.

## Global Constraints

- Verbatim ports (exact `cp`; the overlap service then gets the one noted import rewrite): `api_leprinceos_com/showtimes/services/overlap_service.py` → `cinema/showtimes_overlap.py`, and `www_leprinceos_com/src/pages/EngagementDetail.module.css` → `dashboard/static/dashboard/css/engagement_detail.css`.
- Full overlap handling: single AND bulk create reject runtime-aware overlaps (start + runtime|150 + 30-min buffer). Bulk is all-or-nothing (any existing-or-intra-batch conflict rejects the whole batch). Cancelling a showtime skips the overlap check.
- Showtimes inherit the engagement's screen (`Showtime.save()` defaults `screen_id`); forms expose no screen field. `starts_at` is built aware in `America/New_York`.
- HTMX list-region GETs must return only the partial on `HX-Request` (rule from sub-project 4). Reuse Drawer/Toast/Confirm primitives + the global CSRF hx-headers.
- StaffRequiredMixin on all views; routes under `/dashboard/`. Do NOT modify `cinema` models. Only `cinema/showtimes_overlap.py` (+ its test) and `dashboard/` files change.
- Tests: `python manage.py test cinema dashboard`. Run from repo root with `source .venv/bin/activate`.

---

### Task 1: Overlap service (port) + tests

**Files:**
- Create: `cinema/showtimes_overlap.py` (cp + import rewrite)
- Create: `cinema/tests/test_overlap.py`

**Interfaces:**
- Produces: `cinema.showtimes_overlap` — `OverlapConflict`, `get_effective_end(starts_at, runtime_minutes, buffer=30)`, `check_overlap_against_existing(screen, starts_at, runtime_minutes, film_title, exclude_showtime_id=None) -> list[OverlapConflict]`, `_ProposedShowtime`, `check_intra_batch_overlaps(proposed) -> list[OverlapConflict]`, `format_overlap_error(conflict) -> str`.

- [ ] **Step 1: Write the failing test**

Create `cinema/tests/test_overlap.py`:

```python
import datetime
from zoneinfo import ZoneInfo

from cinema.models import Engagement, EngagementFilm, Film, Screen, Showtime
from cinema.showtimes_overlap import (
    _ProposedShowtime,
    check_intra_batch_overlaps,
    check_overlap_against_existing,
    format_overlap_error,
    get_effective_end,
)
from django.test import TestCase

TZ = ZoneInfo("America/New_York")


def _dt(y, m, d, hh, mm=0):
    return datetime.datetime(y, m, d, hh, mm, tzinfo=TZ)


class OverlapServiceTests(TestCase):
    def setUp(self) -> None:
        self.screen = Screen.objects.create(name="Screen 1", capacity=100)
        self.film = Film.objects.create(title="Dune", runtime_minutes=155)
        self.eng = Engagement.objects.create(
            screen=self.screen, start_date=datetime.date(2026, 7, 1),
            end_date=datetime.date(2026, 7, 31),
        )
        EngagementFilm.objects.create(engagement=self.eng, film=self.film, position=1)

    def test_effective_end_uses_runtime_and_buffer(self) -> None:
        end = get_effective_end(_dt(2026, 7, 4, 19), 100)
        self.assertEqual(end, _dt(2026, 7, 4, 19) + datetime.timedelta(minutes=130))

    def test_effective_end_defaults_when_no_runtime(self) -> None:
        end = get_effective_end(_dt(2026, 7, 4, 19), None)
        self.assertEqual(end, _dt(2026, 7, 4, 19) + datetime.timedelta(minutes=180))

    def test_overlap_against_existing_detected(self) -> None:
        Showtime.objects.create(engagement=self.eng, starts_at=_dt(2026, 7, 4, 19))
        # 155 min + 30 buffer = 185 min -> ends ~22:05; a 21:00 start overlaps
        conflicts = check_overlap_against_existing(
            self.screen, _dt(2026, 7, 4, 21), 155, "Dune")
        self.assertEqual(len(conflicts), 1)

    def test_no_overlap_when_after_effective_end(self) -> None:
        Showtime.objects.create(engagement=self.eng, starts_at=_dt(2026, 7, 4, 19))
        conflicts = check_overlap_against_existing(
            self.screen, _dt(2026, 7, 4, 23), 155, "Dune")
        self.assertEqual(conflicts, [])

    def test_cancelled_excluded(self) -> None:
        Showtime.objects.create(engagement=self.eng, starts_at=_dt(2026, 7, 4, 19), is_cancelled=True)
        conflicts = check_overlap_against_existing(
            self.screen, _dt(2026, 7, 4, 20), 155, "Dune")
        self.assertEqual(conflicts, [])

    def test_exclude_self(self) -> None:
        st = Showtime.objects.create(engagement=self.eng, starts_at=_dt(2026, 7, 4, 19))
        conflicts = check_overlap_against_existing(
            self.screen, _dt(2026, 7, 4, 19), 155, "Dune", exclude_showtime_id=st.pk)
        self.assertEqual(conflicts, [])

    def test_intra_batch_overlap(self) -> None:
        proposed = [
            _ProposedShowtime(0, self.screen, _dt(2026, 7, 4, 19), 155, "Dune"),
            _ProposedShowtime(1, self.screen, _dt(2026, 7, 4, 20), 155, "Dune"),
        ]
        conflicts = check_intra_batch_overlaps(proposed)
        self.assertEqual(len(conflicts), 1)

    def test_format_error_strings(self) -> None:
        Showtime.objects.create(engagement=self.eng, starts_at=_dt(2026, 7, 4, 19))
        c = check_overlap_against_existing(self.screen, _dt(2026, 7, 4, 20), 155, "Dune")[0]
        msg = format_overlap_error(c)
        self.assertIn("overlaps with", msg)
        self.assertIn("Screen 1", msg)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python manage.py test cinema.tests.test_overlap -v 2`
Expected: FAIL — `cinema.showtimes_overlap` missing.

- [ ] **Step 3: Port the overlap service**

```bash
cp /Users/bgoding/code/SoftwareMaine/api_leprinceos_com/showtimes/services/overlap_service.py \
   cinema/showtimes_overlap.py
```

Then edit ONLY the import lines in `cinema/showtimes_overlap.py`: replace

```python
from cinemas.models import Screen
from showtimes.models import Showtime
```

with

```python
from cinema.models import Screen, Showtime
```

Everything else (functions, dataclasses, `total_runtime_minutes`/`display_title`/`engagement_films` usage) is unchanged and already matches the cinema models.

- [ ] **Step 4: Run tests to verify they pass**

Run: `python manage.py test cinema.tests.test_overlap -v 2`
Expected: PASS (8 tests).

- [ ] **Step 5: Commit**

```bash
git add cinema/showtimes_overlap.py cinema/tests/test_overlap.py
git commit -m "feat(cinema): port runtime-aware showtime overlap service"
```

---

### Task 2: Read-only detail page

**Files:**
- Create: `dashboard/static/dashboard/css/engagement_detail.css` (verbatim)
- Create: `dashboard/templates/dashboard/engagement_detail.html`
- Modify: `dashboard/views.py` (replace `EngagementDetailStubView` with `EngagementDetailView`), `dashboard/urls.py`
- Create: `dashboard/tests/test_engagement_detail.py`

**Interfaces:**
- Consumes: `Engagement`, `KIND_LABELS`.
- Produces: `dashboard:engagement_detail` (real). A `#showtime-list` region placeholder (filled in Task 3). Temporary showtime routes so later-task URLs resolve.

- [ ] **Step 1: Write the failing test**

Create `dashboard/tests/test_engagement_detail.py`:

```python
import datetime

from cinema.models import Engagement, EngagementFilm, Film, Screen
from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

User = get_user_model()


def make_eng(screen, films=(), **over):
    defaults = dict(screen=screen, start_date=datetime.date(2026, 7, 1),
                    end_date=datetime.date(2026, 7, 7), status="CONFIRMED")
    defaults.update(over)
    eng = Engagement.objects.create(**defaults)
    for i, f in enumerate(films, start=1):
        EngagementFilm.objects.create(engagement=eng, film=f, position=i)
    return eng


class EngagementDetailPageTests(TestCase):
    def setUp(self) -> None:
        User.objects.create_user(username="s", password="pw12345", is_staff=True)
        self.client.login(username="s", password="pw12345")
        self.screen = Screen.objects.create(name="Screen 1", capacity=100)
        self.film = Film.objects.create(title="Dune", runtime_minutes=155,
                                        poster_url="https://img/d.jpg")

    def test_renders_engagement(self) -> None:
        eng = make_eng(self.screen, films=[self.film], notes="Sold out nightly", kind="CLASSIC")
        html = self.client.get(reverse("dashboard:engagement_detail", args=[eng.pk])).content.decode()
        self.assertIn("Dune", html)
        self.assertIn("Screen 1", html)
        self.assertIn("155 min", html)
        self.assertIn("Classic", html)          # KIND_LABELS
        self.assertIn("Sold out nightly", html) # notes
        self.assertIn("Back to Engagements", html)

    def test_hidden_note(self) -> None:
        eng = make_eng(self.screen, films=[self.film], show_in_main_listings=False)
        html = self.client.get(reverse("dashboard:engagement_detail", args=[eng.pk])).content.decode()
        self.assertIn("Hidden from public listings", html)

    def test_404_missing(self) -> None:
        self.assertEqual(self.client.get(reverse("dashboard:engagement_detail", args=[999])).status_code, 404)

    def test_requires_staff(self) -> None:
        eng = make_eng(self.screen, films=[self.film])
        self.client.logout()
        self.assertEqual(self.client.get(reverse("dashboard:engagement_detail", args=[eng.pk])).status_code, 302)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python manage.py test dashboard.tests.test_engagement_detail -v 2`
Expected: FAIL — stub renders "Coming soon", no film/notes.

- [ ] **Step 3: Copy the detail CSS verbatim**

```bash
cp /Users/bgoding/code/SoftwareMaine/www_leprinceos_com/src/pages/EngagementDetail.module.css \
   dashboard/static/dashboard/css/engagement_detail.css
```

- [ ] **Step 4: Replace the stub view**

In `dashboard/views.py`, remove `EngagementDetailStubView` and add:

```python
class EngagementDetailView(StaffRequiredMixin, TemplateView):
    template_name = "dashboard/engagement_detail.html"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        engagement = get_object_or_404(
            Engagement.objects.select_related("screen").prefetch_related("engagement_films__film"),
            pk=kwargs["pk"],
        )
        ctx["engagement"] = engagement
        ctx["films"] = [ef.film for ef in engagement.engagement_films.all()]
        ctx["showtimes"] = engagement.showtimes.all()
        ctx["KIND_LABELS"] = KIND_LABELS
        return ctx
```

- [ ] **Step 5: Create the detail template**

`dashboard/templates/dashboard/engagement_detail.html`:

```html
{% extends "dashboard/base_dashboard.html" %}
{% load static dashboard_extras %}
{% block title %}{{ engagement.display_title }} · LeprinceOS{% endblock %}
{% block head_extra %}<link rel="stylesheet" href="{% static 'dashboard/css/engagement_detail.css' %}" />{% endblock %}
{% block content %}
<div class="page">
  <div class="header">
    <div>
      <a href="{% url 'dashboard:engagements' %}" class="backLink">&larr; Back to Engagements</a>
      <h1 class="title">{{ engagement.display_title }}</h1>
      <p class="subtitle">Engagement Details &amp; Showtimes</p>
    </div>
  </div>

  <div class="cardsGrid">
    <div class="card">
      <h2 class="cardTitle">Film Details</h2>
      <div class="cardContent">
        {% if films.0.poster_url %}<img src="{{ films.0.poster_url }}" alt="{{ engagement.display_title }}" class="poster" />{% endif %}
        <div class="filmInfo">
          <h3 class="filmTitle">{{ engagement.display_title }}</h3>
          <div class="filmList">
            {% for film in films %}
            <div class="filmRow">
              {% if films|length > 1 %}<span class="filmOrder">{{ forloop.counter }}</span>{% endif %}
              {% if film.poster_url and not forloop.first %}<img src="{{ film.poster_url }}" alt="" class="posterThumb" />{% endif %}
              <div>
                <div class="filmRowTitle">{{ film.title }}</div>
                {% if film.runtime_minutes != None %}<div class="filmRowMeta">{{ film.runtime_minutes }} min</div>{% endif %}
              </div>
            </div>
            {% endfor %}
          </div>
        </div>
      </div>
    </div>

    <div class="card">
      <h2 class="cardTitle">Engagement Details</h2>
      <div class="engagementInfo">
        <div class="infoRow"><span class="label">Status:</span>
          <span class="statusBadge status{{ engagement.status|capfirst }}">{{ engagement.status }}</span></div>
        <div class="infoRow"><span class="label">Kind:</span><span>{{ KIND_LABELS|get_item:engagement.kind }}</span></div>
        {% if engagement.event_title and engagement.event_title != engagement.display_title %}
        <div class="infoRow"><span class="label">Event:</span><span>{{ engagement.event_title }}</span></div>{% endif %}
        {% if not engagement.show_in_main_listings %}
        <div class="infoRow"><span class="hiddenNote">Hidden from public listings</span></div>{% endif %}
        <div class="infoRow"><span class="label">Screen:</span><span>{{ engagement.screen.name }}</span></div>
        <div class="infoRow"><span class="label">Format:</span><span>{{ engagement.presentation_format|upper }}</span></div>
        <div class="infoRow"><span class="label">Start Date:</span><span>{{ engagement.start_date|date:"M j, Y" }}</span></div>
        <div class="infoRow"><span class="label">End Date:</span><span>{{ engagement.end_date|date:"M j, Y" }}</span></div>
        {% if engagement.notes %}<div class="notes"><span class="label">Notes:</span><p>{{ engagement.notes }}</p></div>{% endif %}
      </div>
    </div>
  </div>

  <section class="showtimesSection">
    {% include "dashboard/_showtime_section.html" %}
  </section>
</div>
{% endblock %}
```

Note: the status badge class in the source is `statusConfirmed`/`statusDraft`/`statusCancelled`/`statusEnded`; `status{{ engagement.status|capfirst }}` yields `statusConfirmed` etc. (status values are DRAFT/CONFIRMED/CANCELLED/ENDED → capfirst → Draft/Confirmed/… → `statusConfirmed`). These classes are in the verbatim `engagement_detail.css`.

- [ ] **Step 6: Create a temporary showtime section stub + routes**

Create a temporary `dashboard/templates/dashboard/_showtime_section.html` (replaced in Task 3):

```html
<div class="showtimesHeader"><h2 class="sectionTitle">Showtimes</h2></div>
<div id="showtime-list"></div>
```

In `dashboard/urls.py`, replace the `engagement_detail` stub route and add temporary showtime routes (repointed in Tasks 4–6):

```python
    path("engagements/<int:pk>", views.EngagementDetailView.as_view(), name="engagement_detail"),
    path("engagements/<int:eng_pk>/showtimes/new", views.EngagementDetailView.as_view(), name="showtime_create"),
    path("engagements/<int:eng_pk>/showtimes/bulk", views.EngagementDetailView.as_view(), name="showtime_bulk"),
    path("showtimes/<int:pk>/edit", views.EngagementDetailView.as_view(), name="showtime_edit"),
    path("showtimes/<int:pk>/delete", views.EngagementDetailView.as_view(), name="showtime_delete"),
```

(The showtime_create/bulk/edit/delete targets are placeholders; Tasks 4–6 repoint them.)

- [ ] **Step 7: Run tests to verify they pass**

Run: `python manage.py test dashboard.tests.test_engagement_detail -v 2`
Expected: PASS (4 tests). Then `python manage.py test dashboard` → green.

- [ ] **Step 8: Commit**

```bash
git add cinema/ dashboard/
git commit -m "feat(dashboard): read-only engagement detail page"
```

---

### Task 3: Showtimes list section

**Files:**
- Replace: `dashboard/templates/dashboard/_showtime_section.html` (header + Add/Bulk buttons + list include)
- Create: `dashboard/templates/dashboard/_showtime_list.html`
- Modify: `dashboard/tests/test_engagement_detail.py`

**Interfaces:**
- Produces: `#showtime-list` region rendering the table + cards + empty state; consumed/OOB-refreshed by Tasks 4–6.

- [ ] **Step 1: Write the failing test**

Append to `dashboard/tests/test_engagement_detail.py`:

```python
from cinema.models import Showtime
import datetime as _dt
from django.utils import timezone


class ShowtimeListTests(TestCase):
    def setUp(self) -> None:
        User.objects.create_user(username="s", password="pw12345", is_staff=True)
        self.client.login(username="s", password="pw12345")
        self.screen = Screen.objects.create(name="Screen 1", capacity=100)
        self.film = Film.objects.create(title="Dune", runtime_minutes=155)
        self.eng = make_eng(self.screen, films=[self.film])

    def _url(self, eng):
        return reverse("dashboard:engagement_detail", args=[eng.pk])

    def test_empty_state(self) -> None:
        html = self.client.get(self._url(self.eng)).content.decode()
        self.assertIn("No showtimes scheduled", html)

    def test_lists_showtimes_with_badges(self) -> None:
        aware = timezone.make_aware(_dt.datetime(2026, 7, 4, 19, 0))
        Showtime.objects.create(engagement=self.eng, starts_at=aware, captions="CC")
        Showtime.objects.create(
            engagement=self.eng, starts_at=timezone.make_aware(_dt.datetime(2026, 7, 5, 19, 0)),
            is_cancelled=True)
        html = self.client.get(self._url(self.eng)).content.decode()
        self.assertIn("CC", html)             # captions badge
        self.assertIn("Cancelled", html)      # cancelled badge
        self.assertIn("Active", html)         # active badge
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python manage.py test dashboard.tests.test_engagement_detail.ShowtimeListTests -v 2`
Expected: FAIL — stub section has no showtime rows/empty text.

- [ ] **Step 3: Replace the section template**

`dashboard/templates/dashboard/_showtime_section.html`:

```html
<div class="showtimesHeader">
  <h2 class="sectionTitle">Showtimes</h2>
  <div class="headerActions">
    <button class="primaryButton" hx-get="{% url 'dashboard:showtime_create' engagement.pk %}"
            hx-target="#drawer-content" @click="$store.drawer.show('Add Showtime')">+ Add Showtime</button>
    <button class="secondaryButton" hx-get="{% url 'dashboard:showtime_bulk' engagement.pk %}"
            hx-target="#drawer-content" @click="$store.drawer.show('Bulk Add Showtimes')">Bulk Add</button>
  </div>
</div>
{% include "dashboard/_showtime_list.html" %}
```

- [ ] **Step 4: Create the list partial**

`dashboard/templates/dashboard/_showtime_list.html`:

```html
<div id="showtime-list">
  {% if showtimes %}
  <div class="tableWrapper">
    <table class="table">
      <thead><tr><th>Date &amp; Time</th><th>Screen</th><th>Captions</th><th>Status</th><th>Actions</th></tr></thead>
      <tbody>
        {% for st in showtimes %}
        <tr class="{% if st.is_cancelled %}cancelledRow{% endif %}">
          <td class="dateTimeCell">{{ st.starts_at|date:"D, M j, Y" }} at {{ st.starts_at|date:"g:i A" }}</td>
          <td>{{ st.screen.name }}</td>
          <td>{% if st.captions %}<span class="captionsBadge">{{ st.captions }}</span>{% else %}<span class="noCaptions">—</span>{% endif %}</td>
          <td>{% if st.is_cancelled %}<span class="cancelledBadge">Cancelled</span>{% else %}<span class="activeBadge">Active</span>{% endif %}</td>
          <td>
            <div class="actions">
              <button class="actionButton" hx-get="{% url 'dashboard:showtime_edit' st.pk %}" hx-target="#drawer-content" @click="$store.drawer.show('Edit Showtime')">Edit</button>
              <button class="actionButton deleteButton" hx-post="{% url 'dashboard:showtime_delete' st.pk %}" hx-swap="none"
                      data-dashboard-confirm='{"title":"Delete Showtime","message":"Are you sure you want to delete this showtime?","confirmLabel":"Delete","variant":"danger"}'>Delete</button>
            </div>
          </td>
        </tr>
        {% endfor %}
      </tbody>
    </table>
  </div>
  <div class="cardList">
    {% for st in showtimes %}
    <div class="card {% if st.is_cancelled %}cardCancelled{% endif %}">
      <div class="cardHeader">
        <div class="cardDateTime">{{ st.starts_at|date:"D, M j, Y" }} at {{ st.starts_at|date:"g:i A" }}</div>
        <div class="cardBadges">
          {% if st.is_cancelled %}<span class="cancelledBadge">Cancelled</span>{% else %}<span class="activeBadge">Active</span>{% endif %}
          {% if st.captions %}<span class="captionsBadge">{{ st.captions }}</span>{% endif %}
        </div>
      </div>
      <div class="cardBody"><div class="cardDetail"><span class="cardLabel">Screen</span><span class="cardValue">{{ st.screen.name }}</span></div></div>
      <div class="cardActions">
        <button class="actionButton" hx-get="{% url 'dashboard:showtime_edit' st.pk %}" hx-target="#drawer-content" @click="$store.drawer.show('Edit Showtime')">Edit</button>
        <button class="actionButton deleteButton" hx-post="{% url 'dashboard:showtime_delete' st.pk %}" hx-swap="none"
                data-dashboard-confirm='{"title":"Delete Showtime","message":"Are you sure you want to delete this showtime?","confirmLabel":"Delete","variant":"danger"}'>Delete</button>
      </div>
    </div>
    {% endfor %}
  </div>
  {% else %}
  <div class="empty">
    <p>No showtimes scheduled for this engagement.</p>
    <button class="primaryButton" hx-get="{% url 'dashboard:showtime_create' engagement.pk %}" hx-target="#drawer-content" @click="$store.drawer.show('Add Showtime')">Add your first showtime</button>
  </div>
  {% endif %}
</div>
```

Note: `showtimes` and `engagement` are in the detail page context (Task 2). The mutation views in Tasks 4–6 render this partial with those same context keys for the OOB refresh.

- [ ] **Step 5: Run tests to verify they pass**

Run: `python manage.py test dashboard.tests.test_engagement_detail -v 2`
Expected: PASS. Then `python manage.py test dashboard` → green.

- [ ] **Step 6: Commit**

```bash
git add dashboard/
git commit -m "feat(dashboard): showtimes list (table + cards + empty state)"
```

---

### Task 4: Single showtime create / edit

**Files:**
- Create: `dashboard/templates/dashboard/_showtime_form.html`
- Modify: `dashboard/views.py` (`ShowtimeCreateView`, `ShowtimeEditView` + helpers), `dashboard/urls.py`
- Modify: `dashboard/tests/test_engagement_detail.py`

**Interfaces:**
- Consumes: `check_overlap_against_existing`, `format_overlap_error`, `Showtime`, `_showtime_list.html`.
- Produces: `showtime_create`(eng_pk) GET/POST, `showtime_edit`(pk) GET/POST; a `_showtime_list_response(request, engagement, toast)` OOB helper.

- [ ] **Step 1: Write the failing test**

Append to `dashboard/tests/test_engagement_detail.py`:

```python
import json
from zoneinfo import ZoneInfo

TZ = ZoneInfo("America/New_York")


class ShowtimeCreateEditTests(TestCase):
    def setUp(self) -> None:
        User.objects.create_user(username="s", password="pw12345", is_staff=True)
        self.client.login(username="s", password="pw12345")
        self.screen = Screen.objects.create(name="Screen 1", capacity=100)
        self.film = Film.objects.create(title="Dune", runtime_minutes=155)
        self.eng = make_eng(self.screen, films=[self.film])

    def test_get_form(self) -> None:
        html = self.client.get(reverse("dashboard:showtime_create", args=[self.eng.pk])).content.decode()
        self.assertIn('id="showtime-form"', html)
        self.assertIn("Add Showtime", html)

    def test_create_combines_tz_aware(self) -> None:
        resp = self.client.post(reverse("dashboard:showtime_create", args=[self.eng.pk]),
                                {"date": "2026-07-04", "time": "19:30", "captions": ""})
        self.assertEqual(resp.status_code, 200)
        st = Showtime.objects.get()
        local = st.starts_at.astimezone(TZ)
        self.assertEqual((local.hour, local.minute), (19, 30))
        self.assertEqual(st.screen_id, self.screen.id)  # defaulted from engagement
        self.assertIn("close-drawer", resp["HX-Trigger"])

    def test_create_overlap_rejected(self) -> None:
        import datetime as d
        from django.utils import timezone
        Showtime.objects.create(engagement=self.eng,
                                starts_at=timezone.make_aware(d.datetime(2026, 7, 4, 19, 0)))
        resp = self.client.post(reverse("dashboard:showtime_create", args=[self.eng.pk]),
                                {"date": "2026-07-04", "time": "20:00", "captions": ""})
        self.assertEqual(Showtime.objects.count(), 1)  # not created
        self.assertIn("overlaps with", resp.content.decode())

    def test_edit_cancel_skips_overlap(self) -> None:
        import datetime as d
        from django.utils import timezone
        a = Showtime.objects.create(engagement=self.eng,
                                    starts_at=timezone.make_aware(d.datetime(2026, 7, 4, 19, 0)))
        # editing 'a' to cancelled must not conflict with itself/others
        resp = self.client.post(reverse("dashboard:showtime_edit", args=[a.pk]),
                                {"date": "2026-07-04", "time": "19:00", "captions": "", "is_cancelled": "on"})
        self.assertEqual(resp.status_code, 200)
        a.refresh_from_db()
        self.assertTrue(a.is_cancelled)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python manage.py test dashboard.tests.test_engagement_detail.ShowtimeCreateEditTests -v 2`
Expected: FAIL — form/views absent.

- [ ] **Step 3: Create the form fragment**

`dashboard/templates/dashboard/_showtime_form.html`:

```html
<form id="showtime-form" class="form" hx-post="{{ form_action }}" hx-target="#drawer-content" hx-swap="innerHTML">
  {% csrf_token %}
  {% if errors %}<div class="field-error">{% for e in errors %}{{ e }}<br />{% endfor %}</div>{% endif %}
  <div class="formRow">
    <div class="formGroup">
      <label for="st-date">Date</label>
      <input id="st-date" type="date" name="date" class="input" required value="{{ date }}"
             min="{{ engagement.start_date|date:'Y-m-d' }}" max="{{ engagement.end_date|date:'Y-m-d' }}" />
    </div>
    <div class="formGroup">
      <label for="st-time">Time</label>
      <input id="st-time" type="time" name="time" class="input" required value="{{ time }}" />
    </div>
  </div>
  <div class="formRow">
    <div class="formGroup">
      <label for="st-captions">Captions</label>
      <select id="st-captions" name="captions" class="input">
        <option value="" {% if captions == '' %}selected{% endif %}>None</option>
        <option value="CC" {% if captions == 'CC' %}selected{% endif %}>Closed Captions (CC)</option>
        <option value="OC" {% if captions == 'OC' %}selected{% endif %}>Open Captions (OC)</option>
      </select>
    </div>
    {% if mode == 'edit' %}
    <div class="formGroup">
      <label class="checkboxLabel"><input type="checkbox" name="is_cancelled" {% if is_cancelled %}checked{% endif %} /> Cancelled</label>
    </div>
    {% endif %}
  </div>
</form>
<div id="drawer-footer" class="footer" hx-swap-oob="true">
  <button type="button" class="cancelButton" @click="$store.drawer.close()">Cancel</button>
  <button type="submit" form="showtime-form" class="submitButton">{{ submit_label }}</button>
</div>
```

- [ ] **Step 4: Implement the views + helpers**

In `dashboard/views.py` (imports: `import datetime`, `from zoneinfo import ZoneInfo`, `from cinema.models import Showtime`, `from cinema.showtimes_overlap import check_overlap_against_existing, format_overlap_error`):

```python
CINEMA_TZ = ZoneInfo("America/New_York")


def _showtime_list_response(request, engagement, toast, close_drawer=False):
    ctx = {"engagement": engagement, "showtimes": engagement.showtimes.all()}
    html = render(request, "dashboard/_showtime_list.html", ctx).content.decode()
    html = html.replace('<div id="showtime-list">', '<div id="showtime-list" hx-swap-oob="true">', 1)
    resp = HttpResponse(html)
    trigger = {"dashboard-toast": toast}
    if close_drawer:
        trigger["close-drawer"] = True
    resp["HX-Trigger"] = json.dumps(trigger)
    return resp


def _parse_starts_at(date_str, time_str):
    d = datetime.date.fromisoformat(date_str)
    t = datetime.time.fromisoformat(time_str)
    return datetime.datetime.combine(d, t, tzinfo=CINEMA_TZ)


def _render_showtime_form(request, engagement, action_url, submit_label, mode,
                          date="", time="", captions="", is_cancelled=False, errors=None):
    return render(request, "dashboard/_showtime_form.html", {
        "engagement": engagement, "form_action": action_url, "submit_label": submit_label,
        "mode": mode, "date": date, "time": time, "captions": captions or "",
        "is_cancelled": is_cancelled, "errors": errors or [],
    })


class ShowtimeCreateView(StaffRequiredMixin, View):
    def get(self, request, eng_pk):
        engagement = get_object_or_404(Engagement, pk=eng_pk)
        return _render_showtime_form(
            request, engagement, reverse("dashboard:showtime_create", args=[eng_pk]),
            "Add Showtime", "create", date=engagement.start_date.isoformat())

    def post(self, request, eng_pk):
        engagement = get_object_or_404(Engagement, pk=eng_pk)
        date_str, time_str = request.POST.get("date", ""), request.POST.get("time", "")
        captions = request.POST.get("captions") or None
        action = reverse("dashboard:showtime_create", args=[eng_pk])
        if not date_str or not time_str:
            return _render_showtime_form(request, engagement, action, "Add Showtime", "create",
                                         date=date_str, time=time_str, captions=captions,
                                         errors=["Date and time are required."])
        starts_at = _parse_starts_at(date_str, time_str)
        conflicts = check_overlap_against_existing(
            engagement.screen, starts_at, engagement.total_runtime_minutes, engagement.display_title)
        if conflicts:
            return _render_showtime_form(request, engagement, action, "Add Showtime", "create",
                                         date=date_str, time=time_str, captions=captions,
                                         errors=[format_overlap_error(c) for c in conflicts])
        Showtime.objects.create(engagement=engagement, starts_at=starts_at, captions=captions)
        return _showtime_list_response(request, engagement,
                                       {"kind": "success", "message": "Showtime added"}, close_drawer=True)


class ShowtimeEditView(StaffRequiredMixin, View):
    def get(self, request, pk):
        st = get_object_or_404(Showtime.objects.select_related("engagement"), pk=pk)
        local = st.starts_at.astimezone(CINEMA_TZ)
        return _render_showtime_form(
            request, st.engagement, reverse("dashboard:showtime_edit", args=[pk]),
            "Save Changes", "edit", date=local.date().isoformat(),
            time=local.strftime("%H:%M"), captions=st.captions or "", is_cancelled=st.is_cancelled)

    def post(self, request, pk):
        st = get_object_or_404(Showtime.objects.select_related("engagement"), pk=pk)
        engagement = st.engagement
        date_str, time_str = request.POST.get("date", ""), request.POST.get("time", "")
        captions = request.POST.get("captions") or None
        is_cancelled = request.POST.get("is_cancelled") == "on"
        action = reverse("dashboard:showtime_edit", args=[pk])
        if not date_str or not time_str:
            return _render_showtime_form(request, engagement, action, "Save Changes", "edit",
                                         date=date_str, time=time_str, captions=captions,
                                         is_cancelled=is_cancelled, errors=["Date and time are required."])
        starts_at = _parse_starts_at(date_str, time_str)
        if not is_cancelled:  # cancelling skips the overlap check (matches source)
            conflicts = check_overlap_against_existing(
                engagement.screen, starts_at, engagement.total_runtime_minutes,
                engagement.display_title, exclude_showtime_id=st.pk)
            if conflicts:
                return _render_showtime_form(request, engagement, action, "Save Changes", "edit",
                                             date=date_str, time=time_str, captions=captions,
                                             is_cancelled=is_cancelled,
                                             errors=[format_overlap_error(c) for c in conflicts])
        st.starts_at = starts_at
        st.captions = captions
        st.is_cancelled = is_cancelled
        st.save()
        return _showtime_list_response(request, engagement,
                                       {"kind": "success", "message": "Showtime updated"}, close_drawer=True)
```

Repoint the routes:

```python
    path("engagements/<int:eng_pk>/showtimes/new", views.ShowtimeCreateView.as_view(), name="showtime_create"),
    path("showtimes/<int:pk>/edit", views.ShowtimeEditView.as_view(), name="showtime_edit"),
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `python manage.py test dashboard.tests.test_engagement_detail.ShowtimeCreateEditTests -v 2`
Expected: PASS (4 tests). Then `python manage.py test dashboard` → green.

- [ ] **Step 6: Commit**

```bash
git add dashboard/
git commit -m "feat(dashboard): create/edit showtime (tz-aware + overlap validation)"
```

---

### Task 5: Delete showtime

**Files:**
- Modify: `dashboard/views.py` (`ShowtimeDeleteView`), `dashboard/urls.py`
- Modify: `dashboard/tests/test_engagement_detail.py`

**Interfaces:**
- Consumes: `_showtime_list_response`.
- Produces: `showtime_delete`(pk) POST → delete + OOB `#showtime-list` refresh + toast.

- [ ] **Step 1: Write the failing test**

Append to `dashboard/tests/test_engagement_detail.py`:

```python
class ShowtimeDeleteTests(TestCase):
    def setUp(self) -> None:
        User.objects.create_user(username="s", password="pw12345", is_staff=True)
        self.client.login(username="s", password="pw12345")
        self.screen = Screen.objects.create(name="Screen 1", capacity=100)
        self.film = Film.objects.create(title="Dune", runtime_minutes=155)
        self.eng = make_eng(self.screen, films=[self.film])

    def test_delete(self) -> None:
        import datetime as d
        from django.utils import timezone
        st = Showtime.objects.create(engagement=self.eng,
                                     starts_at=timezone.make_aware(d.datetime(2026, 7, 4, 19, 0)))
        resp = self.client.post(reverse("dashboard:showtime_delete", args=[st.pk]))
        self.assertEqual(resp.status_code, 200)
        self.assertFalse(Showtime.objects.filter(pk=st.pk).exists())
        self.assertIn("dashboard-toast", resp["HX-Trigger"])
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python manage.py test dashboard.tests.test_engagement_detail.ShowtimeDeleteTests -v 2`
Expected: FAIL — delete routes to the detail view.

- [ ] **Step 3: Implement the delete view**

```python
class ShowtimeDeleteView(StaffRequiredMixin, View):
    def post(self, request, pk):
        st = get_object_or_404(Showtime.objects.select_related("engagement"), pk=pk)
        engagement = st.engagement
        st.delete()
        return _showtime_list_response(request, engagement,
                                       {"kind": "success", "message": "Showtime deleted"})
```

Repoint the route:

```python
    path("showtimes/<int:pk>/delete", views.ShowtimeDeleteView.as_view(), name="showtime_delete"),
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python manage.py test dashboard.tests.test_engagement_detail -v 2`
Expected: PASS. Then `python manage.py test dashboard` → green.

- [ ] **Step 5: Commit**

```bash
git add dashboard/
git commit -m "feat(dashboard): delete showtime"
```

---

### Task 6: Bulk add showtimes

**Files:**
- Create: `dashboard/templates/dashboard/_showtime_bulk_form.html`
- Modify: `dashboard/views.py` (`ShowtimeBulkView`), `dashboard/urls.py`, `dashboard/static/dashboard/js/dashboard.js` (`bulkShowtimeForm` Alpine)
- Modify: `dashboard/tests/test_engagement_detail.py`

**Interfaces:**
- Consumes: `check_overlap_against_existing`, `check_intra_batch_overlaps`, `_ProposedShowtime`, `format_overlap_error`, `_showtime_list_response`.
- Produces: `showtime_bulk`(eng_pk) GET form / POST bulk; Alpine `bulkShowtimeForm` (times array).

- [ ] **Step 1: Write the failing test**

Append to `dashboard/tests/test_engagement_detail.py`:

```python
class ShowtimeBulkTests(TestCase):
    def setUp(self) -> None:
        User.objects.create_user(username="s", password="pw12345", is_staff=True)
        self.client.login(username="s", password="pw12345")
        self.screen = Screen.objects.create(name="Screen 1", capacity=100)
        self.film = Film.objects.create(title="Dune", runtime_minutes=100)
        self.eng = make_eng(self.screen, films=[self.film])

    def test_get_bulk_form(self) -> None:
        html = self.client.get(reverse("dashboard:showtime_bulk", args=[self.eng.pk])).content.decode()
        self.assertIn('id="bulk-showtime-form"', html)
        self.assertIn("bulkShowtimeForm", html)

    def test_bulk_creates_grid(self) -> None:
        resp = self.client.post(reverse("dashboard:showtime_bulk", args=[self.eng.pk]),
                                {"start_date": "2026-07-01", "end_date": "2026-07-03",
                                 "times": ["13:00", "19:00"], "captions": ""})
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(Showtime.objects.count(), 6)  # 3 days x 2 times
        self.assertIn("close-drawer", resp["HX-Trigger"])

    def test_bulk_rejects_overlap(self) -> None:
        # two times 30 min apart with a 100-min film overlap -> whole batch rejected
        resp = self.client.post(reverse("dashboard:showtime_bulk", args=[self.eng.pk]),
                                {"start_date": "2026-07-01", "end_date": "2026-07-01",
                                 "times": ["19:00", "19:30"], "captions": ""})
        self.assertEqual(Showtime.objects.count(), 0)
        self.assertIn("overlaps with", resp.content.decode())

    def test_bulk_requires_times(self) -> None:
        resp = self.client.post(reverse("dashboard:showtime_bulk", args=[self.eng.pk]),
                                {"start_date": "2026-07-01", "end_date": "2026-07-01",
                                 "times": ["", ""], "captions": ""})
        self.assertEqual(Showtime.objects.count(), 0)
        self.assertIn("at least one time", resp.content.decode().lower())
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python manage.py test dashboard.tests.test_engagement_detail.ShowtimeBulkTests -v 2`
Expected: FAIL — bulk view/form absent.

- [ ] **Step 3: Create the bulk form fragment**

`dashboard/templates/dashboard/_showtime_bulk_form.html`:

```html
<form id="bulk-showtime-form" class="form" hx-post="{{ form_action }}" hx-target="#drawer-content" hx-swap="innerHTML"
      x-data="bulkShowtimeForm()">
  {% csrf_token %}
  {% if errors %}<div class="field-error">{% for e in errors %}{{ e }}<br />{% endfor %}</div>{% endif %}
  <div class="bulkInfo">Create showtimes for each day in the date range at the specified times.</div>
  <div class="formRow">
    <div class="formGroup"><label for="bulk-start">Start Date</label>
      <input id="bulk-start" type="date" name="start_date" class="input" required value="{{ start_date }}"
             min="{{ engagement.start_date|date:'Y-m-d' }}" max="{{ engagement.end_date|date:'Y-m-d' }}" /></div>
    <div class="formGroup"><label for="bulk-end">End Date</label>
      <input id="bulk-end" type="date" name="end_date" class="input" required value="{{ end_date }}"
             min="{{ engagement.start_date|date:'Y-m-d' }}" max="{{ engagement.end_date|date:'Y-m-d' }}" /></div>
  </div>
  <div class="formGroup">
    <label>Showtimes (per day)</label>
    <div class="timeSlots">
      <template x-for="(t, i) in times" :key="i">
        <div class="timeSlot">
          <input type="time" class="input" required x-model="times[i]" name="times" />
          <button type="button" class="removeTimeButton" x-show="times.length > 1" @click="remove(i)">&times;</button>
        </div>
      </template>
      <button type="button" class="addTimeButton" @click="add()">+ Add another time</button>
    </div>
  </div>
  <div class="formGroup"><label for="bulk-captions">Captions (optional)</label>
    <select id="bulk-captions" name="captions" class="input">
      <option value="" {% if captions == '' %}selected{% endif %}>None</option>
      <option value="CC" {% if captions == 'CC' %}selected{% endif %}>Closed Captions (CC)</option>
      <option value="OC" {% if captions == 'OC' %}selected{% endif %}>Open Captions (OC)</option>
    </select>
  </div>
</form>
<div id="drawer-footer" class="footer" hx-swap-oob="true">
  <button type="button" class="cancelButton" @click="$store.drawer.close()">Cancel</button>
  <button type="submit" form="bulk-showtime-form" class="submitButton">Create Showtimes</button>
</div>
```

- [ ] **Step 4: Add the bulkShowtimeForm Alpine component**

Append to `dashboard/static/dashboard/js/dashboard.js`:

```javascript
document.addEventListener('alpine:init', () => {
  Alpine.data('bulkShowtimeForm', () => ({
    times: [''],
    add() { this.times.push(''); },
    remove(i) { this.times.splice(i, 1); if (!this.times.length) this.times = ['']; },
  }));
});
```

- [ ] **Step 5: Implement the bulk view**

In `dashboard/views.py` (imports: `from django.db import transaction`; `from cinema.showtimes_overlap import check_intra_batch_overlaps, _ProposedShowtime` in addition to the Task-4 imports; `from cinema.models import Screen` already present):

```python
def _render_bulk_form(request, engagement, start_date="", end_date="", captions="", errors=None):
    return render(request, "dashboard/_showtime_bulk_form.html", {
        "engagement": engagement,
        "form_action": reverse("dashboard:showtime_bulk", args=[engagement.pk]),
        "start_date": start_date, "end_date": end_date, "captions": captions or "",
        "errors": errors or [],
    })


class ShowtimeBulkView(StaffRequiredMixin, View):
    def get(self, request, eng_pk):
        engagement = get_object_or_404(Engagement, pk=eng_pk)
        return _render_bulk_form(request, engagement,
                                 start_date=engagement.start_date.isoformat(),
                                 end_date=engagement.end_date.isoformat())

    def post(self, request, eng_pk):
        engagement = get_object_or_404(Engagement, pk=eng_pk)
        start_str, end_str = request.POST.get("start_date", ""), request.POST.get("end_date", "")
        captions = request.POST.get("captions") or None
        times = [t for t in request.POST.getlist("times") if t.strip()]

        def again(errors):
            return _render_bulk_form(request, engagement, start_date=start_str,
                                     end_date=end_str, captions=captions, errors=errors)

        if not start_str or not end_str:
            return again(["Start and end date are required."])
        if not times:
            return again(["Add at least one time."])
        start_date = datetime.date.fromisoformat(start_str)
        end_date = datetime.date.fromisoformat(end_str)
        if end_date < start_date:
            return again(["End date cannot be before start date."])

        screen = engagement.screen
        runtime = engagement.total_runtime_minutes
        title = engagement.display_title
        proposed_showtimes = []
        current = start_date
        one_day = datetime.timedelta(days=1)
        while current <= end_date:
            for t in times:
                starts_at = datetime.datetime.combine(current, datetime.time.fromisoformat(t), tzinfo=CINEMA_TZ)
                proposed_showtimes.append(starts_at)
            current += one_day

        with transaction.atomic():
            Screen.objects.select_for_update().get(pk=screen.pk)
            errors = []
            for starts_at in proposed_showtimes:
                errors += [format_overlap_error(c) for c in check_overlap_against_existing(
                    screen, starts_at, runtime, title)]
            proposed = [_ProposedShowtime(i, screen, s, runtime, title)
                        for i, s in enumerate(proposed_showtimes)]
            errors += [format_overlap_error(c) for c in check_intra_batch_overlaps(proposed)]
            if errors:
                seen, unique = set(), []
                for e in errors:
                    if e not in seen:
                        seen.add(e); unique.append(e)
                return again(unique)
            Showtime.objects.bulk_create([
                Showtime(engagement=engagement, screen=screen, starts_at=s, captions=captions)
                for s in proposed_showtimes])

        return _showtime_list_response(
            request, engagement,
            {"kind": "success", "message": f"Created {len(proposed_showtimes)} showtimes"}, close_drawer=True)
```

Note: `Showtime.save()` defaults screen from the engagement, but `bulk_create` bypasses `save()`, so `screen=screen` is set explicitly on each (as the source does).

Repoint the route:

```python
    path("engagements/<int:eng_pk>/showtimes/bulk", views.ShowtimeBulkView.as_view(), name="showtime_bulk"),
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `python manage.py test dashboard.tests.test_engagement_detail.ShowtimeBulkTests -v 2`
Expected: PASS (4 tests). Then `python manage.py test dashboard cinema` → green.

- [ ] **Step 7: Commit**

```bash
git add dashboard/
git commit -m "feat(dashboard): bulk-add showtimes (date range x times, overlap-checked)"
```

---

### Task 7: Final verification

**Files:** none (verification only).

- [ ] **Step 1: System + migration checks**

Run: `python manage.py check` → no issues.
Run: `python manage.py makemigrations --check --dry-run` → `No changes detected`.

- [ ] **Step 2: Targeted suites**

Run: `python manage.py test cinema dashboard -v 2`
Expected: PASS (overlap service, detail page, showtimes list/create/edit/delete/bulk).

- [ ] **Step 3: Whole project suite (no regressions)**

Run: `python manage.py test`
Expected: PASS.

- [ ] **Step 4: Manual browser smoke (recommended)**

`runserver`, log in as staff, open an engagement's Details: add a showtime; try an overlapping time (conflict message, not created); Bulk Add across the run at two non-overlapping times (verify N created; add/remove time slots); try a bulk overlap (whole batch rejected); edit a showtime to Cancelled (skips overlap); delete one. Compare pixels with the React EngagementDetail page.

---

## Self-Review

**Spec coverage:**
- Overlap service port + tests → Task 1. ✅
- Read-only detail page (info cards, film list, status/kind/notes/hidden) + verbatim CSS, 404 → Task 2. ✅
- Showtimes list (table/cards/empty, cancelled styling) → Task 3. ✅
- Single create/edit (tz-aware combine, overlap, cancel-skips-overlap, captions, is_cancelled edit-only) → Task 4. ✅
- Delete → Task 5. ✅
- Bulk (date range × Alpine time slots, all-or-nothing overlap incl. intra-batch, tz-aware, bulk_create with explicit screen) → Task 6. ✅
- Showtimes inherit engagement screen; HX list-region OOB refresh; staff gate → Tasks 2–6. ✅

**Placeholder scan:** No vague steps; verbatim ports via `cp`+named import rewrite; templates/views/Alpine/tests inlined. Task 2 temporary showtime routes + section stub are explicitly flagged and replaced in Tasks 3–6.

**Type consistency:** `_showtime_list_response(request, engagement, toast, close_drawer)`, `_parse_starts_at(date_str, time_str)`, `_render_showtime_form(...)`, `_render_bulk_form(...)` used consistently. Overlap fns `check_overlap_against_existing`/`check_intra_batch_overlaps`/`_ProposedShowtime`/`format_overlap_error` match the Task-1 module. Alpine `bulkShowtimeForm().times` + `name="times"` inputs → `request.POST.getlist("times")`. `starts_at` built with `tzinfo=CINEMA_TZ` in single + bulk. `#showtime-list` OOB id matches across the partial and both response helpers. Status badge class `status{{ status|capfirst }}` matches the verbatim CSS classes.
