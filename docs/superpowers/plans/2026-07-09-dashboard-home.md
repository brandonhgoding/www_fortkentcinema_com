# Dashboard Home Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** The pixel-faithful `/dashboard/` overview — header, smart alerts, three summary cards, and today's showtimes — replacing the Foundation placeholder Home. This is the final dashboard sub-project.

**Architecture:** `HomeView` computes counts, today's showtimes (tz-aware local-day range), and a server-side smart-alerts list from the `cinema` models; the template ports Home.module.css and renders summary cards, the showtimes table/cards, and dismissible AlertBanner-style banners (Alpine `x-show`, no persistence).

**Tech Stack:** Django 5.2 (USE_TZ, TIME_ZONE=America/New_York), HTMX + Alpine, Django `TestCase`.

## Global Constraints

- Verbatim CSS port: exact `cp` of `www_leprinceos_com/src/pages/Home.module.css` → `dashboard/static/dashboard/css/home.css`.
- All data server-side from `cinema` models; "today"/"tomorrow" are `timezone.localdate()`-based local days converted to aware UTC ranges (`make_aware(datetime.combine(day, time.min))`).
- Summary cards ported WITHOUT trend/previousValue/loading branches (Home never passes them — YAGNI).
- Smart alerts are static server-rendered banners using AlertBanner classnames (`alertContainer`/`alert alert{Type}`/`alertIcon`/`alertMessage`/`dismissButton`), dismissible client-side via Alpine `x-show` with NO persistence (reappear on reload). Do NOT use the Alpine toast store.
- Alert rules (exact, from `useSmartAlerts`): (1) no-showtimes-tomorrow (warning) only when tomorrow has 0 showtimes AND any engagements exist; (2) ending-soon (info) for each CONFIRMED engagement with today ≤ end_date ≤ today+2, message "<display_title> ends in N day(s)"; (3) drafts (info) when draft_count > 0, "You have N draft engagement(s) waiting to be confirmed". Film label uses `display_title`.
- StaffRequiredMixin (already on the placeholder HomeView); no new routes. Do NOT modify `cinema` models. Only `dashboard/` files change.
- Tests: `python manage.py test dashboard`. Run from repo root with `source .venv/bin/activate`.

---

### Task 1: Smart-alerts helper

**Files:**
- Create: `dashboard/smart_alerts.py`
- Create: `dashboard/tests/test_smart_alerts.py`

**Interfaces:**
- Produces: `dashboard.smart_alerts.build_smart_alerts(engagements, tomorrow_showtimes_count, today) -> list[dict]` where each dict is `{"id": str, "type": "warning"|"info", "message": str}`. `engagements` is a queryset/iterable of `Engagement`; `today` is a `datetime.date`.

- [ ] **Step 1: Write the failing test**

Create `dashboard/tests/test_smart_alerts.py`:

```python
import datetime

from cinema.models import Engagement, EngagementFilm, Film, Screen
from dashboard.smart_alerts import build_smart_alerts
from django.test import TestCase


def make_eng(screen, film, *, end, status="CONFIRMED", start=None, title=None):
    eng = Engagement.objects.create(
        screen=screen, start_date=start or datetime.date(2026, 7, 1), end_date=end,
        status=status, event_title=title or "",
    )
    EngagementFilm.objects.create(engagement=eng, film=film, position=1)
    return eng


class BuildSmartAlertsTests(TestCase):
    def setUp(self) -> None:
        self.screen = Screen.objects.create(name="S1", capacity=50)
        self.film = Film.objects.create(title="Dune")
        self.today = datetime.date(2026, 7, 10)

    def test_no_showtimes_tomorrow_only_when_engagements_exist(self) -> None:
        # No engagements -> no alert even if tomorrow empty
        self.assertEqual(build_smart_alerts(Engagement.objects.all(), 0, self.today), [])
        make_eng(self.screen, self.film, end=datetime.date(2026, 7, 20))
        ids = [a["id"] for a in build_smart_alerts(Engagement.objects.all(), 0, self.today)]
        self.assertIn("no-showtimes-tomorrow", ids)

    def test_no_alert_when_tomorrow_has_showtimes(self) -> None:
        make_eng(self.screen, self.film, end=datetime.date(2026, 7, 20))
        ids = [a["id"] for a in build_smart_alerts(Engagement.objects.all(), 3, self.today)]
        self.assertNotIn("no-showtimes-tomorrow", ids)

    def test_ending_soon_boundaries(self) -> None:
        e_today = make_eng(self.screen, self.film, end=self.today, title="Ends Today")
        e_two = make_eng(self.screen, self.film, end=self.today + datetime.timedelta(days=2), title="Ends Two")
        e_three = make_eng(self.screen, self.film, end=self.today + datetime.timedelta(days=3), title="Ends Three")
        e_draft = make_eng(self.screen, self.film, end=self.today, status="DRAFT", title="Draft One")
        alerts = build_smart_alerts(Engagement.objects.all(), 5, self.today)
        msgs = [a["message"] for a in alerts]
        self.assertIn("Ends Today ends in 0 days", msgs)
        self.assertIn("Ends Two ends in 2 days", msgs)
        self.assertFalse(any("Ends Three" in m for m in msgs))   # +3 excluded
        self.assertFalse(any("Draft One" in m for m in msgs))    # non-CONFIRMED excluded

    def test_ending_soon_singular(self) -> None:
        make_eng(self.screen, self.film, end=self.today + datetime.timedelta(days=1), title="One Day")
        msgs = [a["message"] for a in build_smart_alerts(Engagement.objects.all(), 5, self.today)]
        self.assertIn("One Day ends in 1 day", msgs)  # singular

    def test_draft_count_plural(self) -> None:
        make_eng(self.screen, self.film, end=datetime.date(2026, 7, 20), status="DRAFT")
        make_eng(self.screen, self.film, end=datetime.date(2026, 7, 20), status="DRAFT")
        msgs = [a["message"] for a in build_smart_alerts(Engagement.objects.all(), 5, self.today)]
        self.assertIn("You have 2 draft engagements waiting to be confirmed", msgs)

    def test_clean_state_no_alerts(self) -> None:
        make_eng(self.screen, self.film, end=datetime.date(2026, 7, 20))  # confirmed, far end
        alerts = build_smart_alerts(Engagement.objects.all(), 5, self.today)
        self.assertEqual(alerts, [])
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python manage.py test dashboard.tests.test_smart_alerts -v 2`
Expected: FAIL — `dashboard.smart_alerts` missing.

- [ ] **Step 3: Implement the helper**

Create `dashboard/smart_alerts.py`:

```python
from __future__ import annotations

import datetime


def build_smart_alerts(engagements, tomorrow_showtimes_count: int,
                       today: datetime.date) -> list[dict]:
    """Server-side port of the React useSmartAlerts hook.

    engagements: iterable of Engagement (all engagements).
    tomorrow_showtimes_count: number of showtimes scheduled for tomorrow.
    today: local date.
    """
    engagements = list(engagements)
    alerts: list[dict] = []

    if tomorrow_showtimes_count == 0 and engagements:
        alerts.append({
            "id": "no-showtimes-tomorrow", "type": "warning",
            "message": "No showtimes scheduled for tomorrow",
        })

    two_days = today + datetime.timedelta(days=2)
    for e in engagements:
        if e.status != "CONFIRMED":
            continue
        if today <= e.end_date <= two_days:
            days_left = (e.end_date - today).days
            unit = "day" if days_left == 1 else "days"
            alerts.append({
                "id": f"ending-soon-{e.id}", "type": "info",
                "message": f"{e.display_title} ends in {days_left} {unit}",
            })

    draft_count = sum(1 for e in engagements if e.status == "DRAFT")
    if draft_count > 0:
        unit = "engagement" if draft_count == 1 else "engagements"
        alerts.append({
            "id": "draft-engagements", "type": "info",
            "message": f"You have {draft_count} draft {unit} waiting to be confirmed",
        })

    return alerts
```

Note: the source's ending-soon `daysLeft` used `Math.ceil` of a midnight-to-midnight ms diff, which for whole dates equals `(end_date - today).days`. Order matches the source: no-showtimes-tomorrow, then ending-soon (in engagement order), then drafts.

- [ ] **Step 4: Run test to verify it passes**

Run: `python manage.py test dashboard.tests.test_smart_alerts -v 2`
Expected: PASS (6 tests).

- [ ] **Step 5: Commit**

```bash
git add dashboard/smart_alerts.py dashboard/tests/test_smart_alerts.py
git commit -m "feat(dashboard): server-side smart-alerts helper (port of useSmartAlerts)"
```

---

### Task 2: HomeView — counts, today's showtimes, alerts context

**Files:**
- Create: `dashboard/static/dashboard/css/home.css` (verbatim)
- Modify: `dashboard/views.py` (replace placeholder `HomeView`)
- Create: `dashboard/tests/test_home.py`

**Interfaces:**
- Consumes: `build_smart_alerts`, `cinema` models.
- Produces: `HomeView` context keys `active_engagements_count`, `today_showtimes_count`, `screens_count`, `today_showtimes` (ordered qs), `alerts` (list[dict]), `display_name`.

- [ ] **Step 1: Write the failing test**

Create `dashboard/tests/test_home.py`:

```python
import datetime

from cinema.models import Engagement, EngagementFilm, Film, Screen, Showtime
from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

User = get_user_model()


def make_eng(screen, film, *, status="CONFIRMED", start=None, end=None):
    eng = Engagement.objects.create(
        screen=screen, status=status,
        start_date=start or timezone.localdate(),
        end_date=end or timezone.localdate() + datetime.timedelta(days=10),
    )
    EngagementFilm.objects.create(engagement=eng, film=film, position=1)
    return eng


class HomeViewTests(TestCase):
    def setUp(self) -> None:
        User.objects.create_user(username="staffer", password="pw12345", is_staff=True,
                                 first_name="Bran")
        self.client.login(username="staffer", password="pw12345")
        self.screen = Screen.objects.create(name="Screen 1", capacity=100)
        self.film = Film.objects.create(title="Dune", runtime_minutes=155)

    def _local(self, day, hh, mm=0):
        return timezone.make_aware(datetime.datetime.combine(day, datetime.time(hh, mm)))

    def test_counts(self) -> None:
        make_eng(self.screen, self.film, status="CONFIRMED")
        make_eng(self.screen, self.film, status="DRAFT")
        Screen.objects.create(name="Screen 2", capacity=60)
        resp = self.client.get(reverse("dashboard:home"))
        ctx = resp.context
        self.assertEqual(ctx["active_engagements_count"], 1)   # only CONFIRMED
        self.assertEqual(ctx["screens_count"], 2)

    def test_today_showtimes_tz_correct(self) -> None:
        eng = make_eng(self.screen, self.film)
        today = timezone.localdate()
        # 23:00 local today -> counts today, not tomorrow
        Showtime.objects.create(engagement=eng, starts_at=self._local(today, 23, 0))
        # tomorrow -> excluded
        Showtime.objects.create(engagement=eng,
                                starts_at=self._local(today + datetime.timedelta(days=1), 12, 0))
        resp = self.client.get(reverse("dashboard:home"))
        self.assertEqual(resp.context["today_showtimes_count"], 1)

    def test_display_name_first_name(self) -> None:
        resp = self.client.get(reverse("dashboard:home"))
        self.assertEqual(resp.context["display_name"], "Bran")

    def test_requires_staff(self) -> None:
        self.client.logout()
        self.assertEqual(self.client.get(reverse("dashboard:home")).status_code, 302)
        User.objects.create_user(username="p", password="pw12345", is_staff=False)
        self.client.login(username="p", password="pw12345")
        self.assertEqual(self.client.get(reverse("dashboard:home")).status_code, 403)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python manage.py test dashboard.tests.test_home -v 2`
Expected: FAIL — placeholder HomeView has no counts/context.

- [ ] **Step 3: Copy the Home CSS verbatim**

```bash
cp /Users/bgoding/code/SoftwareMaine/www_leprinceos_com/src/pages/Home.module.css \
   dashboard/static/dashboard/css/home.css
```

- [ ] **Step 4: Replace the HomeView**

In `dashboard/views.py`, replace the placeholder `HomeView` (the `class HomeView(StaffRequiredMixin, TemplateView): template_name = "dashboard/home.html"`) with (imports needed: `import datetime`, `from django.utils import timezone`, `from cinema.models import Engagement, Screen, Showtime` — most already imported; `from .smart_alerts import build_smart_alerts`):

```python
class HomeView(StaffRequiredMixin, TemplateView):
    template_name = "dashboard/home.html"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        today = timezone.localdate()
        tomorrow = today + datetime.timedelta(days=1)
        day_after = today + datetime.timedelta(days=2)

        def day_range(d1, d2):
            start = timezone.make_aware(datetime.datetime.combine(d1, datetime.time.min))
            end = timezone.make_aware(datetime.datetime.combine(d2, datetime.time.min))
            return start, end

        today_start, today_end = day_range(today, tomorrow)
        tomo_start, tomo_end = day_range(tomorrow, day_after)

        today_showtimes = (
            Showtime.objects.filter(starts_at__gte=today_start, starts_at__lt=today_end)
            .select_related("screen")
            .prefetch_related("engagement__engagement_films__film")
            .order_by("starts_at")
        )
        tomorrow_count = Showtime.objects.filter(
            starts_at__gte=tomo_start, starts_at__lt=tomo_end).count()

        engagements = list(
            Engagement.objects.prefetch_related("engagement_films__film"))

        user = self.request.user
        ctx.update({
            "active_engagements_count": sum(1 for e in engagements if e.status == "CONFIRMED"),
            "screens_count": Screen.objects.count(),
            "today_showtimes": today_showtimes,
            "today_showtimes_count": today_showtimes.count(),
            "alerts": build_smart_alerts(engagements, tomorrow_count, today),
            "display_name": user.get_short_name() or user.get_username(),
        })
        return ctx
```

Note: `active_engagements_count` is computed from the already-fetched `engagements` list (reused by `build_smart_alerts`), avoiding a second query. `get_short_name()` returns `first_name` (may be empty) → falls back to username, matching `first_name || username`.

- [ ] **Step 5: Run tests to verify they pass**

Run: `python manage.py test dashboard.tests.test_home -v 2`
Expected: PASS (4 tests). (The template still renders the old placeholder body; that's fine — Task 3 rewrites it. The context tests pass now.) Then `python manage.py test dashboard` → green.

- [ ] **Step 6: Commit**

```bash
git add dashboard/views.py dashboard/static/dashboard/css/home.css dashboard/tests/test_home.py
git commit -m "feat(dashboard): HomeView counts + today's showtimes + alerts context"
```

---

### Task 3: Home template (cards, showtimes, alerts)

**Files:**
- Replace: `dashboard/templates/dashboard/home.html`
- Create: `dashboard/templates/dashboard/_alerts.html`
- Modify: `dashboard/tests/test_home.py` (rendered-output tests)

**Interfaces:**
- Consumes: the `HomeView` context (`active_engagements_count`, `today_showtimes_count`, `screens_count`, `today_showtimes`, `alerts`, `display_name`).

- [ ] **Step 1: Write the failing test**

Append to `dashboard/tests/test_home.py`:

```python
class HomeRenderTests(TestCase):
    def setUp(self) -> None:
        User.objects.create_user(username="s", password="pw12345", is_staff=True)
        self.client.login(username="s", password="pw12345")
        self.screen = Screen.objects.create(name="Screen 1", capacity=100)
        self.film = Film.objects.create(title="Dune", runtime_minutes=155)

    def _local(self, day, hh, mm=0):
        return timezone.make_aware(datetime.datetime.combine(day, datetime.time(hh, mm)))

    def test_cards_and_links(self) -> None:
        html = self.client.get(reverse("dashboard:home")).content.decode()
        self.assertIn("Active Engagements", html)
        self.assertIn("Today's Showtimes", html)
        self.assertIn("Screens", html)
        self.assertIn(reverse("dashboard:engagements"), html)
        self.assertIn(reverse("dashboard:screens"), html)
        self.assertIn("summaryGrid", html)

    def test_today_showtimes_table(self) -> None:
        eng = make_eng(self.screen, self.film)
        Showtime.objects.create(engagement=eng, starts_at=self._local(timezone.localdate(), 19, 30))
        html = self.client.get(reverse("dashboard:home")).content.decode()
        self.assertIn("Dune", html)
        self.assertIn("Screen 1", html)
        self.assertIn("Active", html)

    def test_empty_state(self) -> None:
        html = self.client.get(reverse("dashboard:home")).content.decode()
        self.assertIn("No Showtimes Today", html)

    def test_alerts_rendered(self) -> None:
        # a confirmed engagement with no showtimes tomorrow -> no-showtimes-tomorrow warning
        make_eng(self.screen, self.film)
        html = self.client.get(reverse("dashboard:home")).content.decode()
        self.assertIn("No showtimes scheduled for tomorrow", html)
        self.assertIn("alertContainer", html)
        self.assertIn("dismissButton", html)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python manage.py test dashboard.tests.test_home.HomeRenderTests -v 2`
Expected: FAIL — placeholder template lacks cards/showtimes/alerts.

- [ ] **Step 3: Create the alerts partial**

`dashboard/templates/dashboard/_alerts.html`:

```html
{% if alerts %}
<div class="alertContainer">
  {% for alert in alerts %}
  <div class="alert alert{{ alert.type|capfirst }}" role="alert" aria-live="polite"
       x-data="{ shown: true }" x-show="shown">
    <div class="alertIcon">{% if alert.type == 'warning' %}⚠{% elif alert.type == 'success' %}✓{% elif alert.type == 'error' %}✕{% else %}ℹ{% endif %}</div>
    <p class="alertMessage">{{ alert.message }}</p>
    <button type="button" class="dismissButton" aria-label="Dismiss alert" @click="shown = false"><span aria-hidden="true">&times;</span></button>
  </div>
  {% endfor %}
</div>
{% endif %}
```

Note: `alert{{ alert.type|capfirst }}` yields `alertWarning`/`alertInfo` — the alert `type` values are already lowercase (`warning`/`info`), so `capfirst` correctly produces the camelCase class matching `alertbanner.css` (unlike the all-caps status-badge case). These classes exist in the Foundation-ported `alertbanner.css`.

- [ ] **Step 4: Replace the home template**

`dashboard/templates/dashboard/home.html`:

```html
{% extends "dashboard/base_dashboard.html" %}
{% load static %}
{% block title %}Dashboard · LeprinceOS{% endblock %}
{% block head_extra %}<link rel="stylesheet" href="{% static 'dashboard/css/home.css' %}" />{% endblock %}
{% block content %}
<div class="dashboardHome">
  <div class="pageHeader">
    <h1 class="pageTitle">Dashboard</h1>
    <p class="welcomeText">Welcome back, {{ display_name }}</p>
  </div>

  {% include "dashboard/_alerts.html" %}

  <div class="summaryGrid">
    <div class="card"><div class="cardBody">
      <p class="cardLabel">Active Engagements</p>
      <p class="cardValue">{{ active_engagements_count }}</p>
      <a href="{% url 'dashboard:engagements' %}" class="cardLink">View all &rarr;</a>
    </div></div>
    <div class="card"><div class="cardBody">
      <p class="cardLabel">Today's Showtimes</p>
      <p class="cardValue">{{ today_showtimes_count }}</p>
    </div></div>
    <div class="card"><div class="cardBody">
      <p class="cardLabel">Screens</p>
      <p class="cardValue">{{ screens_count }}</p>
      <a href="{% url 'dashboard:screens' %}" class="cardLink">Manage &rarr;</a>
    </div></div>
  </div>

  <section class="section">
    <h2 class="sectionTitle">Today's Showtimes</h2>
    {% if today_showtimes %}
    <div class="tableCard">
      <div class="tableWrapper">
        <table class="table">
          <thead><tr><th>Time</th><th>Film</th><th>Screen</th><th>Format</th><th>Status</th></tr></thead>
          <tbody>
            {% for st in today_showtimes %}
            <tr>
              <td class="timeCell">{{ st.starts_at|date:"g:i A" }}</td>
              <td class="filmCell">{{ st.engagement.display_title }}</td>
              <td class="screenCell">{{ st.screen.name }}</td>
              <td class="formatCell">{{ st.engagement.presentation_format|upper }}</td>
              <td>{% if st.is_cancelled %}<span class="statusCancelled">Cancelled</span>{% else %}<span class="statusActive">Active</span>{% endif %}</td>
            </tr>
            {% endfor %}
          </tbody>
        </table>
      </div>
    </div>
    <div class="cardList">
      {% for st in today_showtimes %}
      <div class="showtimeCard">
        <div class="showtimeCardHeader">
          <span class="showtimeTime">{{ st.starts_at|date:"g:i A" }}</span>
          {% if st.is_cancelled %}<span class="statusCancelled">Cancelled</span>{% else %}<span class="statusActive">Active</span>{% endif %}
        </div>
        <div class="showtimeCardBody">
          <h3 class="showtimeFilm">{{ st.engagement.display_title }}</h3>
          <div class="showtimeMeta"><span>{{ st.screen.name }}</span><span class="showtimeFormat">{{ st.engagement.presentation_format|upper }}</span></div>
        </div>
      </div>
      {% endfor %}
    </div>
    {% else %}
    <div class="empty-state">
      <div class="empty-state-icon" style="font-size: 2.5rem;">🎬</div>
      <h3 class="empty-state-title">No Showtimes Today</h3>
      <p class="empty-state-description">Get started by creating an engagement and scheduling showtimes for your films.</p>
      <a href="{% url 'dashboard:engagements' %}" class="btn btn-primary">View Engagements</a>
    </div>
    {% endif %}
  </section>
</div>
{% endblock %}
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `python manage.py test dashboard.tests.test_home -v 2`
Expected: PASS (all home tests). Then `python manage.py test dashboard` → green.

- [ ] **Step 6: Commit**

```bash
git add dashboard/templates/dashboard/home.html dashboard/templates/dashboard/_alerts.html dashboard/tests/test_home.py
git commit -m "feat(dashboard): Home template (summary cards, today's showtimes, dismissible alerts)"
```

---

### Task 4: Final verification

**Files:** none (verification only).

- [ ] **Step 1: System + migration checks**

Run: `python manage.py check` → no issues.
Run: `python manage.py makemigrations --check --dry-run` → `No changes detected`.

- [ ] **Step 2: Dashboard suite**

Run: `python manage.py test dashboard -v 2`
Expected: PASS (smart-alerts, home view + render, and all prior dashboard tests).

- [ ] **Step 3: Whole project suite (no regressions)**

Run: `python manage.py test`
Expected: PASS — `web`/`blog`/`cinema`/`dashboard`.

- [ ] **Step 4: Manual browser smoke (recommended)**

`runserver`, log in as staff, open `/dashboard/`: confirm the three counts, the welcome name, today's showtimes table/cards (seed a CONFIRMED engagement + a showtime today), the 🎬 empty state when none, and the three alert types (draft engagement present → drafts info; a CONFIRMED engagement ending within 2 days → ending-soon; no showtimes tomorrow → warning). Dismiss an alert (hides until reload). Compare pixels with the React Home page.

---

## Self-Review

**Spec coverage:**
- Smart-alerts helper (3 rules, pluralization, display_title, order) → Task 1. ✅
- HomeView counts (active CONFIRMED / screens / today's showtimes tz-correct) + alerts context + display_name → Task 2. ✅
- Summary cards (no trend/loading), today's showtimes table+cards+empty state, dismissible AlertBanner alerts, verbatim home.css → Task 3. ✅
- Staff gate (inherited), no new routes, only dashboard/ → all tasks. ✅
- Out of scope (trends, Alt+N, mutations) → not present. ✅

**Placeholder scan:** No vague steps; home.css via `cp`; helper/view/templates/tests inlined.

**Type consistency:** `build_smart_alerts(engagements, tomorrow_showtimes_count, today)` signature matches its Task-2 call (`build_smart_alerts(engagements, tomorrow_count, today)`). Context keys (`active_engagements_count`, `today_showtimes_count`, `screens_count`, `today_showtimes`, `alerts`, `display_name`) match between Task 2 (produced) and Task 3 (consumed). Alert dict keys (`id`/`type`/`message`) match between the helper and `_alerts.html`. `alert{{ type|capfirst }}` → alertWarning/alertInfo (types are lowercase, so capfirst is correct here — contrast the status-badge all-caps case). `display_title`/`screen.name`/`presentation_format` are real cinema-model attributes used consistently.
