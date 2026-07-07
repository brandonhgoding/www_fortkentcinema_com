# Dashboard Engagements Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** The pixel-faithful Engagements page over `cinema.Engagement` — filter-tab list with inline status control, and a create/edit drawer whose form embeds the FilmSearchCombo and manages the ordered film set (single film or double-feature ordering).

**Architecture:** Class-based `dashboard` views return HTML fragments; the list is a composite date+status queryset swapped per tab; the create/edit drawer posts ordered film ids that the view writes as `EngagementFilm` rows (position) in a transaction; inline status change and delete re-render the `#engagement-list` region out-of-band. Films are held client-side in an Alpine component fed by the combo's `film-selected` event.

**Tech Stack:** Django 5.2, HTMX + Alpine (vendored), Django `TestCase`.

## Global Constraints

- Verbatim CSS ports are exact `cp` from leprinceos sources: `www_leprinceos_com/src/pages/Engagements.module.css` and `src/components/StatusDropdown.module.css`.
- Reuse the FilmSearchCombo partial (`dashboard/templates/dashboard/_film_search_combo.html`) and its `film-selected` event ({id,title,poster}); reuse Drawer/Toast/Confirm primitives; CSRF is already global (`hx-headers` on `<body>`).
- All views use `StaffRequiredMixin`; routes under `/dashboard/`, namespace `dashboard`.
- Badge kind labels (KIND_LABELS): REGULAR→"Regular", SPECIAL_EVENT→**"Event"**, CLASSIC→"Classic", DOUBLE_FEATURE→"Double Feature". Form-select kind labels (KIND_OPTIONS) differ: SPECIAL_EVENT→**"Special Event"**. Keep both; the divergence is intentional. Form status choices: DRAFT/CONFIRMED/CANCELLED only (ENDED is date-derived, never manually set).
- Do NOT modify the `cinema` models. Only `dashboard/` files change.
- Tests use `django.test.TestCase`, run with `python manage.py test dashboard`.
- Run from repo root with `source .venv/bin/activate`.

---

### Task 1: Engagement list + filter tabs

**Files:**
- Create: `dashboard/static/dashboard/css/engagements.css` (verbatim)
- Create: `dashboard/templates/dashboard/engagements.html`, `dashboard/templates/dashboard/_engagement_list.html`
- Modify: `dashboard/views.py` (replace `EngagementsStubView` with `EngagementListView`; add `EngagementDetailStubView` + tab/label helpers), `dashboard/urls.py`
- Create: `dashboard/tests/test_engagements.py`

**Interfaces:**
- Produces: `dashboard:engagements` (list, `?tab=`), `dashboard:engagement_detail` (stub); `engagement_queryset(tab)` and `KIND_LABELS`; `#engagement-list` region rendering the table + cards; a `tab` context var.

- [ ] **Step 1: Write the failing test**

Create `dashboard/tests/test_engagements.py`:

```python
import datetime

from cinema.models import Engagement, EngagementFilm, Film, Screen
from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

User = get_user_model()


def make_engagement(screen, *, start, end, status="CONFIRMED", kind="REGULAR",
                    films=(), show=True, event_title=""):
    eng = Engagement.objects.create(
        screen=screen, start_date=start, end_date=end, status=status, kind=kind,
        show_in_main_listings=show, event_title=event_title,
    )
    for i, f in enumerate(films, start=1):
        EngagementFilm.objects.create(engagement=eng, film=f, position=i)
    return eng


class EngagementListTests(TestCase):
    def setUp(self) -> None:
        User.objects.create_user(username="s", password="pw12345", is_staff=True)
        self.client.login(username="s", password="pw12345")
        self.screen = Screen.objects.create(name="Screen 1", capacity=100)
        self.film = Film.objects.create(title="Jaws", poster_url="https://img/j.jpg")
        self.today = timezone.localdate()

    def test_current_tab_default(self) -> None:
        make_engagement(self.screen, start=self.today - datetime.timedelta(days=1),
                        end=self.today + datetime.timedelta(days=1), films=[self.film])
        html = self.client.get(reverse("dashboard:engagements")).content.decode()
        self.assertIn("Jaws", html)
        self.assertIn("Screen 1", html)

    def test_upcoming_excludes_current(self) -> None:
        make_engagement(self.screen, start=self.today - datetime.timedelta(days=1),
                        end=self.today + datetime.timedelta(days=1), films=[self.film])
        html = self.client.get(reverse("dashboard:engagements"), {"tab": "UPCOMING"}).content.decode()
        self.assertNotIn("Jaws", html)
        self.assertIn("empty-state", html)

    def test_draft_tab(self) -> None:
        make_engagement(self.screen, start=self.today, end=self.today, status="DRAFT",
                        films=[self.film])
        html = self.client.get(reverse("dashboard:engagements"), {"tab": "DRAFT"}).content.decode()
        self.assertIn("Jaws", html)

    def test_kind_and_hidden_badges(self) -> None:
        make_engagement(self.screen, start=self.today, end=self.today, kind="CLASSIC",
                        films=[self.film], show=False, event_title="Noir Night")
        html = self.client.get(reverse("dashboard:engagements")).content.decode()
        self.assertIn("Classic", html)   # kind badge
        self.assertIn("Hidden", html)    # hidden badge

    def test_detail_stub_resolves(self) -> None:
        self.assertEqual(reverse("dashboard:engagement_detail", args=[1]), "/dashboard/engagements/1")

    def test_requires_staff(self) -> None:
        self.client.logout()
        self.assertEqual(self.client.get(reverse("dashboard:engagements")).status_code, 302)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python manage.py test dashboard.tests.test_engagements -v 2`
Expected: FAIL — stub view renders "Coming soon"; detail route missing.

- [ ] **Step 3: Copy the engagements CSS verbatim**

```bash
cp /Users/bgoding/code/SoftwareMaine/www_leprinceos_com/src/pages/Engagements.module.css \
   dashboard/static/dashboard/css/engagements.css
```

- [ ] **Step 4: Add helpers + list view (replace the stub)**

In `dashboard/views.py` add (imports: `import datetime`, `from django.utils import timezone`, `from cinema.models import Engagement, EngagementFilm` — Screen/Film already imported):

```python
KIND_LABELS = {"REGULAR": "Regular", "SPECIAL_EVENT": "Event", "CLASSIC": "Classic",
               "DOUBLE_FEATURE": "Double Feature"}
ENGAGEMENT_TABS = ["CURRENT", "UPCOMING", "DRAFT", "ENDED", "CANCELLED"]


def engagement_queryset(tab: str):
    today = timezone.localdate()
    qs = Engagement.objects.select_related("screen").prefetch_related("engagement_films__film")
    if tab == "UPCOMING":
        return qs.filter(status="CONFIRMED", start_date__gt=today)
    if tab == "ENDED":
        return qs.filter(end_date__lt=today)
    if tab == "DRAFT":
        return qs.filter(status="DRAFT")
    if tab == "CANCELLED":
        return qs.filter(status="CANCELLED")
    # CURRENT (default)
    return qs.filter(status="CONFIRMED", start_date__lte=today, end_date__gte=today)


def engagement_list_context(request):
    tab = request.GET.get("tab") or "CURRENT"
    if tab not in ENGAGEMENT_TABS:
        tab = "CURRENT"
    return {
        "engagements": engagement_queryset(tab),
        "tab": tab,
        "tabs": ENGAGEMENT_TABS,
        "KIND_LABELS": KIND_LABELS,
        "today": timezone.localdate(),
    }


class EngagementListView(StaffRequiredMixin, TemplateView):
    template_name = "dashboard/engagements.html"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx.update(engagement_list_context(self.request))
        return ctx


class EngagementDetailStubView(StaffRequiredMixin, TemplateView):
    template_name = "dashboard/_stub_page.html"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["page_title"] = "Engagement detail"
        return ctx
```

- [ ] **Step 5: Create the list templates**

`dashboard/templates/dashboard/engagements.html`:

```html
{% extends "dashboard/base_dashboard.html" %}
{% load static %}
{% block title %}Engagements · LeprinceOS{% endblock %}
{% block head_extra %}<link rel="stylesheet" href="{% static 'dashboard/css/engagements.css' %}" />{% endblock %}
{% block content %}
<div class="page">
  <div class="header">
    <div>
      <h1 class="title">Engagements</h1>
      <p class="subtitle">Manage your film engagements and runs.</p>
    </div>
    <button class="primaryButton" hx-get="{% url 'dashboard:engagement_create' %}"
            hx-target="#drawer-content" @click="$store.drawer.show('New Engagement')">+ New Engagement</button>
  </div>

  <div class="filter-tabs" role="tablist">
    {% for t in tabs %}
    <button class="filter-tab {% if t == tab %}active{% endif %}" role="tab"
            hx-get="{% url 'dashboard:engagements' %}?tab={{ t }}"
            hx-target="#engagement-list" hx-swap="outerHTML"
            hx-push-url="true">{{ t|capfirst }}</button>
    {% endfor %}
  </div>

  {% include "dashboard/_engagement_list.html" %}
</div>
{% endblock %}
```

`dashboard/templates/dashboard/_engagement_list.html`:

```html
{% load dashboard_extras %}
<div id="engagement-list" data-tab="{{ tab }}">
  {% if engagements %}
  <div class="tableWrapper">
    <table class="table">
      <thead><tr><th>Film</th><th>Screen</th><th>Dates</th><th>Format</th><th>Status</th><th>Actions</th></tr></thead>
      <tbody>
        {% for e in engagements %}
        <tr>
          <td>
            <div class="filmCell">
              {% with p=e.primary_film %}{% if p and p.poster_url %}<img src="{{ p.poster_url }}" alt="" class="posterThumb" />{% endif %}{% endwith %}
              <span class="filmTitle">{{ e.display_title }}</span>
              {% if e.kind != 'REGULAR' %}<span class="kindBadge">{{ KIND_LABELS|get_item:e.kind }}</span>{% endif %}
              {% if not e.show_in_main_listings %}<span class="hiddenBadge" title="Hidden from public listings">Hidden</span>{% endif %}
            </div>
          </td>
          <td>{{ e.screen.name }}</td>
          <td>{{ e.start_date|date:"M j, Y" }} - {{ e.end_date|date:"M j, Y" }}</td>
          <td class="formatCell">{{ e.presentation_format|upper }}</td>
          <td>{% include "dashboard/_status_dropdown.html" with engagement=e %}</td>
          <td>
            <div class="actions">
              <a href="{% url 'dashboard:engagement_detail' e.pk %}" class="actionButton detailsButton">Details</a>
              <button class="actionButton" hx-get="{% url 'dashboard:engagement_edit' e.pk %}" hx-target="#drawer-content" @click="$store.drawer.show('Edit Engagement')">Edit</button>
              <button class="actionButton deleteButton" hx-post="{% url 'dashboard:engagement_delete' e.pk %}?tab={{ tab }}" hx-target="#engagement-list" hx-swap="outerHTML"
                      data-dashboard-confirm='{"title":"Delete Engagement","message":"Are you sure you want to delete the engagement for \"{{ e.display_title|escapejs }}\"?","confirmLabel":"Delete","variant":"danger"}'>Delete</button>
            </div>
          </td>
        </tr>
        {% endfor %}
      </tbody>
    </table>
  </div>

  <div class="cardList">
    {% for e in engagements %}
    <div class="card">
      <div class="cardHeader">
        {% with p=e.primary_film %}{% if p and p.poster_url %}<img src="{{ p.poster_url }}" alt="" class="cardPoster" />{% endif %}{% endwith %}
        <div class="cardTitleSection">
          <h3 class="cardTitle">{{ e.display_title }}</h3>
          {% if e.kind != 'REGULAR' %}<span class="kindBadge">{{ KIND_LABELS|get_item:e.kind }}</span>{% endif %}
          {% if not e.show_in_main_listings %}<span class="hiddenBadge" title="Hidden from public listings">Hidden</span>{% endif %}
          <div class="cardBadges">
            {% include "dashboard/_status_dropdown.html" with engagement=e %}
            <span class="formatBadge">{{ e.presentation_format|upper }}</span>
          </div>
        </div>
      </div>
      <div class="cardBody">
        <div class="cardDetail"><span class="cardLabel">Screen</span><span class="cardValue">{{ e.screen.name }}</span></div>
        <div class="cardDetail"><span class="cardLabel">Dates</span><span class="cardValue">{{ e.start_date|date:"M j, Y" }} - {{ e.end_date|date:"M j, Y" }}</span></div>
      </div>
      <div class="cardActions">
        <a href="{% url 'dashboard:engagement_detail' e.pk %}" class="actionButton detailsButton">Details</a>
        <button class="actionButton" hx-get="{% url 'dashboard:engagement_edit' e.pk %}" hx-target="#drawer-content" @click="$store.drawer.show('Edit Engagement')">Edit</button>
        <button class="actionButton deleteButton" hx-post="{% url 'dashboard:engagement_delete' e.pk %}?tab={{ tab }}" hx-target="#engagement-list" hx-swap="outerHTML"
                data-dashboard-confirm='{"title":"Delete Engagement","message":"Are you sure you want to delete the engagement for \"{{ e.display_title|escapejs }}\"?","confirmLabel":"Delete","variant":"danger"}'>Delete</button>
      </div>
    </div>
    {% endfor %}
  </div>
  {% else %}
  <div class="empty-state">
    <div class="empty-state-icon" style="font-size: 2.5rem;">🎬</div>
    <h3 class="empty-state-title">No {{ tab|lower }} engagements</h3>
    <p class="empty-state-description">Nothing here for this filter. Create an engagement or switch tabs.</p>
  </div>
  {% endif %}
</div>
```

Note: this list template references `_status_dropdown.html` (Task 2) and the `engagement_create`/`engagement_edit`/`engagement_delete` URLs (Tasks 3–5). To keep Task 1 runnable, create a minimal `_status_dropdown.html` stub now (`<span class="status-badge status-{{ engagement.status|lower }}">{{ engagement.status|capfirst }}</span>`) and add temporary routes (below) pointing at `EngagementListView`; Tasks 2–5 replace them.

- [ ] **Step 6: Add routes (with temporaries) + stub status partial**

Create `dashboard/templates/dashboard/_status_dropdown.html` (temporary — replaced in Task 2):

```html
<span class="status-badge status-{{ engagement.status|lower }}">{{ engagement.status|capfirst }}</span>
```

In `dashboard/urls.py`, replace the `engagements` stub route and add the rest:

```python
    path("engagements", views.EngagementListView.as_view(), name="engagements"),
    path("engagements/<int:pk>", views.EngagementDetailStubView.as_view(), name="engagement_detail"),
    path("engagements/new", views.EngagementListView.as_view(), name="engagement_create"),
    path("engagements/<int:pk>/edit", views.EngagementListView.as_view(), name="engagement_edit"),
    path("engagements/<int:pk>/delete", views.EngagementListView.as_view(), name="engagement_delete"),
    path("engagements/<int:pk>/status", views.EngagementListView.as_view(), name="engagement_status"),
```

(The `engagement_create/edit/delete/status` targets are temporary placeholders; Tasks 2–5 repoint them at real views.)

- [ ] **Step 7: Run tests to verify they pass**

Run: `python manage.py test dashboard.tests.test_engagements -v 2`
Expected: PASS (6 tests). Then `python manage.py test dashboard` → green.

- [ ] **Step 8: Commit**

```bash
git add dashboard/
git commit -m "feat(dashboard): Engagements list with filter tabs (table + cards)"
```

---

### Task 2: Inline StatusDropdown

**Files:**
- Create: `dashboard/static/dashboard/css/status_dropdown.css` (verbatim)
- Replace: `dashboard/templates/dashboard/_status_dropdown.html` (real dropdown)
- Modify: `dashboard/views.py` (`EngagementStatusView`), `dashboard/urls.py` (repoint `engagement_status`), `dashboard/static/dashboard/js/dashboard.js` (`statusDropdown` Alpine), `dashboard/templates/dashboard/engagements.html` (link status_dropdown.css)
- Modify: `dashboard/tests/test_engagements.py`

**Interfaces:**
- Consumes: the `#engagement-list` OOB refresh helper.
- Produces: `dashboard:engagement_status` (POST `status`, `?tab=`) → OOB `#engagement-list` refresh (filtered by tab) + toast; `_status_dropdown.html` with the Alpine `statusDropdown` (locked when ENDED or ended-by-date).

- [ ] **Step 1: Write the failing test**

Append to `dashboard/tests/test_engagements.py`:

```python
import json


class EngagementStatusTests(TestCase):
    def setUp(self) -> None:
        User.objects.create_user(username="s", password="pw12345", is_staff=True)
        self.client.login(username="s", password="pw12345")
        self.screen = Screen.objects.create(name="S1", capacity=50)
        self.today = timezone.localdate()

    def test_status_change_updates_and_refreshes(self) -> None:
        e = make_engagement(self.screen, start=self.today, end=self.today, status="DRAFT")
        resp = self.client.post(reverse("dashboard:engagement_status", args=[e.pk]) + "?tab=DRAFT",
                                {"status": "CONFIRMED"})
        self.assertEqual(resp.status_code, 200)
        e.refresh_from_db()
        self.assertEqual(e.status, "CONFIRMED")
        self.assertIn('id="engagement-list"', resp.content.decode())
        self.assertIn("dashboard-toast", resp["HX-Trigger"])

    def test_status_rejects_ended_value(self) -> None:
        e = make_engagement(self.screen, start=self.today, end=self.today, status="DRAFT")
        resp = self.client.post(reverse("dashboard:engagement_status", args=[e.pk]),
                                {"status": "ENDED"})
        e.refresh_from_db()
        self.assertEqual(e.status, "DRAFT")  # ENDED not manually settable
        self.assertEqual(resp.status_code, 400)

    def test_ended_engagement_locked(self) -> None:
        past = self.today - datetime.timedelta(days=5)
        e = make_engagement(self.screen, start=past, end=past, status="CONFIRMED")
        html = self.client.get(reverse("dashboard:engagements"), {"tab": "ENDED"}).content.decode()
        # locked: the status button is disabled for an ended engagement
        self.assertIn("disabled", html)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python manage.py test dashboard.tests.test_engagements.EngagementStatusTests -v 2`
Expected: FAIL — status view is the list-view placeholder; no real dropdown.

- [ ] **Step 3: Copy the StatusDropdown CSS verbatim + link it**

```bash
cp /Users/bgoding/code/SoftwareMaine/www_leprinceos_com/src/components/StatusDropdown.module.css \
   dashboard/static/dashboard/css/status_dropdown.css
```

In `engagements.html` `head_extra`, add after the engagements.css link:

```html
<link rel="stylesheet" href="{% static 'dashboard/css/status_dropdown.css' %}" />
```

- [ ] **Step 4: Replace the status dropdown partial**

`dashboard/templates/dashboard/_status_dropdown.html`:

```html
{% with locked=engagement.is_ended_or_past %}
<div class="statusDropdown" x-data="statusDropdown">
  <button type="button" class="status-badge status-{{ engagement.status|lower }} statusButton"
          @click="open = !open"
          {% if locked %}disabled{% endif %}
          aria-haspopup="listbox" :aria-expanded="open">
    {{ engagement.get_status_display }}
    {% if not locked %}<span class="chevron" aria-hidden="true">▼</span>{% endif %}
  </button>
  {% if not locked %}
  <div class="dropdown" role="listbox" x-show="open" x-cloak @click.outside="open = false" @keydown.escape.window="open = false">
    {% for value, label in status_options %}
    <button type="button" role="option" class="dropdownItem {% if value == engagement.status %}currentItem{% endif %}"
            {% if value == engagement.status %}disabled{% endif %}
            hx-post="{% url 'dashboard:engagement_status' engagement.pk %}?tab={{ tab }}"
            hx-vals='{"status": "{{ value }}"}' hx-swap="none" @click="open = false">
      <div class="statusOption">
        <span class="status-badge status-{{ value|lower }} optionBadge">{{ label }}</span>
        {% if value == engagement.status %}<span class="checkmark" aria-label="Current status">✓</span>{% endif %}
      </div>
      <p class="statusDescription">{{ status_descriptions|get_item:value }}</p>
    </button>
    {% endfor %}
  </div>
  {% endif %}
</div>
{% endwith %}
```

This needs `status_options` (list of (value,label) for DRAFT/CONFIRMED/CANCELLED), `status_descriptions` map, and `tab` available where the partial renders. Add them to the list context and pass `engagement.is_ended_or_past`. Because `is_ended_or_past` is not on the model (do NOT edit cinema), compute a per-engagement flag in the template instead: replace `engagement.is_ended_or_past` with a comparison — pass `today` into the include and use `{% with locked=engagement.status == 'ENDED' or engagement.end_date < today %}`. Update the partial's first line to:

```html
{% with locked=engagement.status == 'ENDED' or engagement.end_date < today %}
```

Add to `engagement_list_context` (Task 1) the extra keys:

```python
    "status_options": [("DRAFT", "Draft"), ("CONFIRMED", "Confirmed"), ("CANCELLED", "Cancelled")],
    "status_descriptions": {"DRAFT": "Not yet confirmed", "CONFIRMED": "Active engagement",
                            "CANCELLED": "Engagement cancelled", "ENDED": "Engagement has ended"},
```

Ensure the `{% include ... with engagement=e %}` calls also pass `today` and the two maps — since they're in the render context already (list context), included partials inherit them; pass `today=today` explicitly in the include is unnecessary because context vars are inherited. Confirm `today` is in `engagement_list_context` (it is).

- [ ] **Step 5: Add the statusDropdown Alpine component**

Append to `dashboard/static/dashboard/js/dashboard.js`:

```javascript
document.addEventListener('alpine:init', () => {
  Alpine.data('statusDropdown', () => ({ open: false }));
});
```

- [ ] **Step 6: Implement the status view + OOB list helper**

In `dashboard/views.py` add a shared OOB list-refresh helper and the view:

```python
def _engagement_list_response(request, tab, toast=None, status_code=200):
    ctx = {**engagement_list_context(request), "tab": tab, "engagements": engagement_queryset(tab)}
    html = render(request, "dashboard/_engagement_list.html", ctx).content.decode()
    html = html.replace('<div id="engagement-list"', '<div id="engagement-list" hx-swap-oob="true"', 1)
    resp = HttpResponse(html, status=status_code)
    trigger = {}
    if toast:
        trigger["dashboard-toast"] = toast
    if trigger:
        resp["HX-Trigger"] = json.dumps(trigger)
    return resp


class EngagementStatusView(StaffRequiredMixin, View):
    def post(self, request, pk):
        engagement = get_object_or_404(Engagement, pk=pk)
        new_status = request.POST.get("status")
        if new_status not in {"DRAFT", "CONFIRMED", "CANCELLED"}:
            return HttpResponse(status=400)
        engagement.status = new_status
        engagement.save(update_fields=["status"])
        tab = request.GET.get("tab") or "CURRENT"
        return _engagement_list_response(request, tab, toast={"kind": "success", "message": "Status updated"})
```

Note: `engagement_list_context` reads `request.GET.get("tab")`; the status POST carries `?tab=` so the refreshed list stays on the active tab (and correctly drops an engagement that no longer matches).

Repoint the route in `dashboard/urls.py`:

```python
    path("engagements/<int:pk>/status", views.EngagementStatusView.as_view(), name="engagement_status"),
```

- [ ] **Step 7: Run tests to verify they pass**

Run: `python manage.py test dashboard.tests.test_engagements -v 2`
Expected: PASS. Then `python manage.py test dashboard` → green.

- [ ] **Step 8: Commit**

```bash
git add dashboard/
git commit -m "feat(dashboard): inline engagement StatusDropdown (tab-aware list refresh)"
```

---

### Task 3: Delete engagement

**Files:**
- Modify: `dashboard/views.py` (`EngagementDeleteView`), `dashboard/urls.py`
- Modify: `dashboard/tests/test_engagements.py`

**Interfaces:**
- Consumes: `_engagement_list_response`.
- Produces: `dashboard:engagement_delete` (POST, `?tab=`) → cascade-delete + OOB list refresh + toast.

- [ ] **Step 1: Write the failing test**

Append to `dashboard/tests/test_engagements.py`:

```python
class EngagementDeleteTests(TestCase):
    def setUp(self) -> None:
        User.objects.create_user(username="s", password="pw12345", is_staff=True)
        self.client.login(username="s", password="pw12345")
        self.screen = Screen.objects.create(name="S1", capacity=50)
        self.today = timezone.localdate()

    def test_delete_cascades(self) -> None:
        f = Film.objects.create(title="X")
        e = make_engagement(self.screen, start=self.today, end=self.today, films=[f])
        resp = self.client.post(reverse("dashboard:engagement_delete", args=[e.pk]) + "?tab=CURRENT")
        self.assertEqual(resp.status_code, 200)
        self.assertFalse(Engagement.objects.filter(pk=e.pk).exists())
        self.assertEqual(EngagementFilm.objects.count(), 0)  # cascaded
        self.assertIn("dashboard-toast", resp["HX-Trigger"])
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python manage.py test dashboard.tests.test_engagements.EngagementDeleteTests -v 2`
Expected: FAIL — delete routes to list view (no deletion).

- [ ] **Step 3: Implement the delete view**

In `dashboard/views.py`:

```python
class EngagementDeleteView(StaffRequiredMixin, View):
    def post(self, request, pk):
        engagement = get_object_or_404(Engagement, pk=pk)
        engagement.delete()
        tab = request.GET.get("tab") or "CURRENT"
        return _engagement_list_response(request, tab, toast={"kind": "success", "message": "Engagement deleted"})
```

Repoint the route:

```python
    path("engagements/<int:pk>/delete", views.EngagementDeleteView.as_view(), name="engagement_delete"),
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python manage.py test dashboard.tests.test_engagements -v 2`
Expected: PASS. Then `python manage.py test dashboard` → green.

- [ ] **Step 5: Commit**

```bash
git add dashboard/
git commit -m "feat(dashboard): delete engagement (cascade + list refresh)"
```

---

### Task 4: Create engagement (form + Alpine film-set)

**Files:**
- Create: `dashboard/forms.py` addition (`EngagementForm`)
- Create: `dashboard/templates/dashboard/_engagement_form.html`
- Modify: `dashboard/views.py` (`EngagementCreateView` + film-set save helper), `dashboard/urls.py`, `dashboard/static/dashboard/js/dashboard.js` (`engagementForm` Alpine)
- Modify: `dashboard/tests/test_engagements.py`

**Interfaces:**
- Consumes: `EngagementForm`, `_film_search_combo.html`, the `film-selected` event, `_engagement_list_response`.
- Produces: `dashboard:engagement_create` (GET form / POST create); `save_engagement_films(engagement, film_ids)`; the Alpine `engagementForm` component (films array, kind behavior, hidden `films` inputs).

- [ ] **Step 1: Write the failing test**

Append to `dashboard/tests/test_engagements.py`:

```python
class EngagementCreateTests(TestCase):
    def setUp(self) -> None:
        User.objects.create_user(username="s", password="pw12345", is_staff=True)
        self.client.login(username="s", password="pw12345")
        self.screen = Screen.objects.create(name="S1", capacity=50)
        self.f1 = Film.objects.create(title="A")
        self.f2 = Film.objects.create(title="B")
        self.today = timezone.localdate()

    def _payload(self, **over):
        data = {
            "kind": "REGULAR", "event_title": "", "screen": self.screen.pk,
            "start_date": self.today.isoformat(), "end_date": self.today.isoformat(),
            "presentation_format": "2d", "status": "DRAFT", "show_in_main_listings": "on",
            "notes": "", "films": [self.f1.pk],
        }
        data.update(over)
        return data

    def test_get_form(self) -> None:
        html = self.client.get(reverse("dashboard:engagement_create")).content.decode()
        self.assertIn('id="engagement-form"', html)
        self.assertIn("Create Engagement", html)

    def test_create_single_film(self) -> None:
        resp = self.client.post(reverse("dashboard:engagement_create") + "?tab=DRAFT", self._payload())
        self.assertEqual(resp.status_code, 200)
        e = Engagement.objects.get()
        self.assertEqual(list(e.engagement_films.values_list("film_id", "position")), [(self.f1.pk, 1)])
        self.assertIn("close-drawer", resp["HX-Trigger"])

    def test_create_double_feature_orders_films(self) -> None:
        resp = self.client.post(reverse("dashboard:engagement_create"),
                                self._payload(kind="DOUBLE_FEATURE", films=[self.f2.pk, self.f1.pk]))
        self.assertEqual(resp.status_code, 200)
        e = Engagement.objects.get()
        self.assertEqual(list(e.engagement_films.values_list("film_id", "position")),
                         [(self.f2.pk, 1), (self.f1.pk, 2)])

    def test_double_feature_requires_two(self) -> None:
        resp = self.client.post(reverse("dashboard:engagement_create"),
                                self._payload(kind="DOUBLE_FEATURE", films=[self.f1.pk]))
        self.assertEqual(Engagement.objects.count(), 0)
        self.assertIn("at least two", resp.content.decode().lower())

    def test_missing_film(self) -> None:
        resp = self.client.post(reverse("dashboard:engagement_create"), self._payload(films=[]))
        self.assertEqual(Engagement.objects.count(), 0)
        self.assertIn('id="engagement-form"', resp.content.decode())

    def test_end_before_start(self) -> None:
        resp = self.client.post(reverse("dashboard:engagement_create"),
                                self._payload(end_date=(self.today - datetime.timedelta(days=1)).isoformat()))
        self.assertEqual(Engagement.objects.count(), 0)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python manage.py test dashboard.tests.test_engagements.EngagementCreateTests -v 2`
Expected: FAIL — create view/form absent.

- [ ] **Step 3: Add the EngagementForm**

Append to `dashboard/forms.py`:

```python
from cinema.models import Engagement

KIND_OPTIONS = [("REGULAR", "Regular"), ("SPECIAL_EVENT", "Special Event"),
                ("CLASSIC", "Classic"), ("DOUBLE_FEATURE", "Double Feature")]
STATUS_OPTIONS = [("DRAFT", "Draft"), ("CONFIRMED", "Confirmed"), ("CANCELLED", "Cancelled")]


class EngagementForm(forms.ModelForm):
    kind = forms.ChoiceField(choices=KIND_OPTIONS, widget=forms.Select(attrs={"class": "input"}))
    status = forms.ChoiceField(choices=STATUS_OPTIONS, widget=forms.Select(attrs={"class": "input"}))

    class Meta:
        model = Engagement
        fields = ["kind", "event_title", "screen", "start_date", "end_date",
                  "presentation_format", "status", "show_in_main_listings", "notes"]
        widgets = {
            "event_title": forms.TextInput(attrs={"class": "input", "placeholder": "e.g. Creature Double Feature"}),
            "screen": forms.Select(attrs={"class": "input"}),
            "start_date": forms.DateInput(attrs={"class": "input", "type": "date"}, format="%Y-%m-%d"),
            "end_date": forms.DateInput(attrs={"class": "input", "type": "date"}, format="%Y-%m-%d"),
            "presentation_format": forms.Select(attrs={"class": "input"}),
            "notes": forms.Textarea(attrs={"class": "textarea", "rows": 3,
                                           "placeholder": "Optional notes about this engagement..."}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["screen"].empty_label = "Select a screen"
        for name in ("start_date", "end_date"):
            self.fields[name].input_formats = ["%Y-%m-%d"]
```

- [ ] **Step 4: Create the form fragment**

`dashboard/templates/dashboard/_engagement_form.html`:

```html
{{ initial_films|json_script:"engagement-initial-films" }}
<form id="engagement-form" class="form" hx-post="{{ form_action }}" hx-target="#drawer-content" hx-swap="innerHTML"
      x-data="engagementForm()" data-initial-kind="{{ form.kind.value|default:'REGULAR' }}">
  {% csrf_token %}
  {% if form.non_field_errors or film_error %}<div class="field-error">{{ form.non_field_errors|striptags }} {{ film_error }}</div>{% endif %}

  <div class="formGroup">
    <label for="{{ form.kind.id_for_label }}">Type</label>
    <select id="{{ form.kind.id_for_label }}" name="kind" class="input" x-model="kind" @change="onKindChange()">
      {% for value, label in kind_options %}<option value="{{ value }}" {% if form.kind.value == value %}selected{% endif %}>{{ label }}</option>{% endfor %}
    </select>
  </div>

  <!-- Film picker -->
  <div class="formGroup">
    <label x-text="kind === 'DOUBLE_FEATURE' ? 'Films (in play order)' : 'Film'"></label>
    <template x-if="kind === 'DOUBLE_FEATURE' && films.length">
      <ol class="filmList">
        <template x-for="(f, idx) in films" :key="f.id">
          <li class="filmListItem">
            <span class="filmListOrder" x-text="idx + 1"></span>
            <template x-if="f.poster"><img :src="f.poster" alt="" class="posterThumb" /></template>
            <span class="filmListTitle" x-text="f.title"></span>
            <button type="button" class="removeFilmButton" @click="removeFilm(f.id)">Remove</button>
          </li>
        </template>
      </ol>
    </template>
    <template x-if="kind !== 'DOUBLE_FEATURE' && films.length">
      <div class="selectedFilm"><span class="checkIcon">✓</span><span x-text="'Selected: ' + films[0].title"></span></div>
    </template>
    {% include "dashboard/_film_search_combo.html" with combo_id="engagement-film" %}
    <template x-if="kind === 'DOUBLE_FEATURE' && films.length < 2">
      <p class="fieldHint">Add at least two films for a double feature.</p>
    </template>
    <template x-for="f in films" :key="'in-' + f.id"><input type="hidden" name="films" :value="f.id" /></template>
  </div>

  <div class="formGroup" x-show="kind !== 'REGULAR'">
    <label for="{{ form.event_title.id_for_label }}">Event Title (optional)</label>
    {{ form.event_title }}
  </div>

  <div class="formGroup">
    <label for="{{ form.screen.id_for_label }}">Screen</label>
    {{ form.screen }}
    {% if form.screen.errors %}<div class="field-error">{{ form.screen.errors|striptags }}</div>{% endif %}
  </div>

  <div class="formRow">
    <div class="formGroup"><label for="{{ form.start_date.id_for_label }}">Start Date</label>{{ form.start_date }}{% if form.start_date.errors %}<div class="field-error">{{ form.start_date.errors|striptags }}</div>{% endif %}</div>
    <div class="formGroup"><label for="{{ form.end_date.id_for_label }}">End Date</label>{{ form.end_date }}{% if form.end_date.errors %}<div class="field-error">{{ form.end_date.errors|striptags }}</div>{% endif %}</div>
  </div>

  <div class="formRow">
    <div class="formGroup"><label for="{{ form.presentation_format.id_for_label }}">Format</label>{{ form.presentation_format }}</div>
    <div class="formGroup"><label for="{{ form.status.id_for_label }}">Status</label>{{ form.status }}</div>
  </div>

  <div class="formGroup"><label class="checkboxLabel">{{ form.show_in_main_listings }} Show in main listings</label></div>
  <div class="formGroup"><label for="{{ form.notes.id_for_label }}">Notes</label>{{ form.notes }}</div>
</form>
<div id="drawer-footer" class="footer" hx-swap-oob="true">
  <button type="button" class="cancelButton" @click="$store.drawer.close()">Cancel</button>
  <button type="submit" form="engagement-form" class="submitButton">{{ submit_label }}</button>
</div>
```

- [ ] **Step 5: Add the engagementForm Alpine component**

Append to `dashboard/static/dashboard/js/dashboard.js`:

```javascript
document.addEventListener('alpine:init', () => {
  Alpine.data('engagementForm', () => ({
    films: [],
    kind: 'REGULAR',
    init() {
      const el = document.getElementById('engagement-initial-films');
      this.films = el ? JSON.parse(el.textContent) : [];
      this.kind = this.$root.dataset.initialKind || 'REGULAR';
      // film-selected fires on document.body from BOTH the local combo $dispatch
      // (bubbles up) and the server TMDB-import HX-Trigger. Only one engagement
      // form exists at a time, so apply unconditionally.
      this._onSel = (e) => this.addFilm(e.detail);
      document.body.addEventListener('film-selected', this._onSel);
    },
    destroy() { document.body.removeEventListener('film-selected', this._onSel); },
    addFilm(film) {
      if (this.kind === 'DOUBLE_FEATURE') {
        if (!this.films.some((f) => f.id === film.id)) this.films.push({ id: film.id, title: film.title, poster: film.poster });
      } else {
        this.films = [{ id: film.id, title: film.title, poster: film.poster }];
      }
    },
    removeFilm(id) { this.films = this.films.filter((f) => f.id !== id); },
    onKindChange() {
      if (this.kind !== 'DOUBLE_FEATURE') this.films = this.films.slice(0, 1);
    },
  }));
});
```

- [ ] **Step 6: Implement the create view + film-set save helper**

In `dashboard/views.py` (imports: `from django.db import transaction`, `from .forms import EngagementForm`, `import json`):

```python
def save_engagement_films(engagement, film_ids):
    engagement.engagement_films.all().delete()
    for pos, fid in enumerate(film_ids, start=1):
        EngagementFilm.objects.create(engagement=engagement, film_id=fid, position=pos)


def _film_ids(request):
    ids = []
    for raw in request.POST.getlist("films"):
        try:
            ids.append(int(raw))
        except (TypeError, ValueError):
            continue
    # preserve order, drop duplicates
    seen = set()
    return [i for i in ids if not (i in seen or seen.add(i))]


def _validate_film_set(kind, film_ids):
    if kind == "DOUBLE_FEATURE":
        return None if len(film_ids) >= 2 else "Add at least two films for a double feature."
    return None if len(film_ids) == 1 else "Select a film for this engagement."


def _render_engagement_form(request, form, action_url, submit_label, film_ids, film_error=None):
    from .forms import KIND_OPTIONS
    initial = [{"id": f.id, "title": f.title, "poster": f.poster_url}
               for f in Film.objects.filter(id__in=film_ids)]
    # keep submitted order
    order = {fid: i for i, fid in enumerate(film_ids)}
    initial.sort(key=lambda d: order.get(d["id"], 0))
    return render(request, "dashboard/_engagement_form.html", {
        "form": form, "form_action": action_url, "submit_label": submit_label,
        "kind_options": KIND_OPTIONS, "film_error": film_error,
        "initial_films": initial,
    })


class EngagementCreateView(StaffRequiredMixin, View):
    def get(self, request):
        return _render_engagement_form(request, EngagementForm(),
                                       reverse("dashboard:engagement_create"), "Create Engagement", [])

    def post(self, request):
        form = EngagementForm(request.POST)
        film_ids = _film_ids(request)
        film_error = _validate_film_set(request.POST.get("kind", "REGULAR"), film_ids)
        # validate film films exist
        if film_ids and Film.objects.filter(id__in=film_ids).count() != len(film_ids):
            film_error = "One or more selected films no longer exist."
        if form.is_valid() and not film_error:
            with transaction.atomic():
                engagement = form.save()
                save_engagement_films(engagement, film_ids)
            tab = request.GET.get("tab") or "CURRENT"
            resp = _engagement_list_response(request, tab, toast={"kind": "success", "message": "Engagement created"})
            existing = resp["HX-Trigger"]
            trigger = json.loads(existing) if existing else {}
            trigger["close-drawer"] = True
            resp["HX-Trigger"] = json.dumps(trigger)
            return resp
        return _render_engagement_form(request, form, reverse("dashboard:engagement_create"),
                                       "Create Engagement", film_ids, film_error)
```

Repoint the route:

```python
    path("engagements/new", views.EngagementCreateView.as_view(), name="engagement_create"),
```

- [ ] **Step 7: Run tests to verify they pass**

Run: `python manage.py test dashboard.tests.test_engagements.EngagementCreateTests -v 2`
Expected: PASS (6 tests). Then `python manage.py test dashboard` → green.

- [ ] **Step 8: Commit**

```bash
git add dashboard/
git commit -m "feat(dashboard): create engagement via drawer (Alpine film-set + ordered EngagementFilm)"
```

---

### Task 5: Edit engagement (prefill + replace film set)

**Files:**
- Modify: `dashboard/views.py` (`EngagementEditView`), `dashboard/urls.py`
- Modify: `dashboard/tests/test_engagements.py`

**Interfaces:**
- Consumes: `EngagementForm`, `_render_engagement_form`, `save_engagement_films`, `_engagement_list_response`.
- Produces: `dashboard:engagement_edit` (GET prefilled / POST update+replace films).

- [ ] **Step 1: Write the failing test**

Append to `dashboard/tests/test_engagements.py`:

```python
class EngagementEditTests(TestCase):
    def setUp(self) -> None:
        User.objects.create_user(username="s", password="pw12345", is_staff=True)
        self.client.login(username="s", password="pw12345")
        self.screen = Screen.objects.create(name="S1", capacity=50)
        self.f1 = Film.objects.create(title="A")
        self.f2 = Film.objects.create(title="B")
        self.today = timezone.localdate()

    def test_get_prefilled(self) -> None:
        e = make_engagement(self.screen, start=self.today, end=self.today, films=[self.f1])
        html = self.client.get(reverse("dashboard:engagement_edit", args=[e.pk])).content.decode()
        self.assertIn("Save Changes", html)
        self.assertIn('"title": "A"', html)  # initial_films_json seeds the Alpine state

    def test_edit_replaces_film_set(self) -> None:
        e = make_engagement(self.screen, start=self.today, end=self.today,
                            kind="DOUBLE_FEATURE", films=[self.f1, self.f2])
        data = {
            "kind": "DOUBLE_FEATURE", "event_title": "", "screen": self.screen.pk,
            "start_date": self.today.isoformat(), "end_date": self.today.isoformat(),
            "presentation_format": "2d", "status": "DRAFT", "show_in_main_listings": "on",
            "notes": "", "films": [self.f2.pk, self.f1.pk],  # reversed order
        }
        resp = self.client.post(reverse("dashboard:engagement_edit", args=[e.pk]), data)
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(list(e.engagement_films.values_list("film_id", "position")),
                         [(self.f2.pk, 1), (self.f1.pk, 2)])
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python manage.py test dashboard.tests.test_engagements.EngagementEditTests -v 2`
Expected: FAIL — edit routes to the list view.

- [ ] **Step 3: Implement the edit view**

In `dashboard/views.py`:

```python
class EngagementEditView(StaffRequiredMixin, View):
    def get(self, request, pk):
        engagement = get_object_or_404(Engagement, pk=pk)
        film_ids = list(engagement.engagement_films.order_by("position").values_list("film_id", flat=True))
        return _render_engagement_form(request, EngagementForm(instance=engagement),
                                       reverse("dashboard:engagement_edit", args=[pk]), "Save Changes", film_ids)

    def post(self, request, pk):
        engagement = get_object_or_404(Engagement, pk=pk)
        form = EngagementForm(request.POST, instance=engagement)
        film_ids = _film_ids(request)
        film_error = _validate_film_set(request.POST.get("kind", "REGULAR"), film_ids)
        if film_ids and Film.objects.filter(id__in=film_ids).count() != len(film_ids):
            film_error = "One or more selected films no longer exist."
        if form.is_valid() and not film_error:
            with transaction.atomic():
                engagement = form.save()
                save_engagement_films(engagement, film_ids)
            tab = request.GET.get("tab") or "CURRENT"
            resp = _engagement_list_response(request, tab, toast={"kind": "success", "message": "Engagement updated"})
            trigger = json.loads(resp["HX-Trigger"]) if resp.get("HX-Trigger") else {}
            trigger["close-drawer"] = True
            resp["HX-Trigger"] = json.dumps(trigger)
            return resp
        return _render_engagement_form(request, form, reverse("dashboard:engagement_edit", args=[pk]),
                                       "Save Changes", film_ids, film_error)
```

Repoint the route:

```python
    path("engagements/<int:pk>/edit", views.EngagementEditView.as_view(), name="engagement_edit"),
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python manage.py test dashboard.tests.test_engagements -v 2`
Expected: PASS (all engagement tests). Then `python manage.py test dashboard` → green.

- [ ] **Step 5: Commit**

```bash
git add dashboard/
git commit -m "feat(dashboard): edit engagement (prefill + replace film set)"
```

---

### Task 6: Final verification

**Files:** none (verification only).

- [ ] **Step 1: System + migration checks**

Run: `python manage.py check` → no issues.
Run: `python manage.py makemigrations --check --dry-run` → `No changes detected`.

- [ ] **Step 2: Dashboard suite**

Run: `python manage.py test dashboard -v 2`
Expected: PASS (engagements list/tabs/status/delete/create/edit + all prior).

- [ ] **Step 3: Whole project suite (no regressions)**

Run: `python manage.py test`
Expected: PASS.

- [ ] **Step 4: Manual browser smoke (recommended)**

`runserver`, log in as staff, `/dashboard/engagements`: switch tabs (Current/Upcoming/Draft/Ended/Cancelled); flip a status inline (confirm it can drop off the current tab); open "New Engagement" — pick a single film via the combo, save; create a Double Feature — add two films (verify order + Remove), save; edit one (film set replaced); delete one (themed confirm). Compare pixels with the React Engagements page.

---

## Self-Review

**Spec coverage:**
- Filter-tab composite querysets + list table/cards + empty states + verbatim CSS → Task 1. ✅
- Inline StatusDropdown (Alpine + verbatim CSS) + tab-aware list refresh, ENDED lock → Task 2. ✅
- Delete (cascade) + confirm → Task 3. ✅
- Create form (EngagementForm + Alpine film-set, single/double ordering, validation, transaction, EngagementFilm positions) → Task 4. ✅
- Edit (prefill + replace film set) → Task 5. ✅
- Stub `engagement_detail` route for the Details link → Task 1. ✅
- Single FilmSearchCombo reused; `film-selected` consumed by `engagementForm` → Task 4. ✅
- Staff gate; only dashboard/ changed → all tasks. ✅

**Placeholder scan:** No vague steps; verbatim CSS via `cp`; templates/views/Alpine/tests inlined. Task 1's temporary routes + status-dropdown stub are explicitly flagged and replaced in Tasks 2–5 (same pattern as Screens/Films).

**Type consistency:** `engagement_queryset(tab)`/`engagement_list_context(request)`/`_engagement_list_response(request, tab, toast)` used consistently across list/status/delete/create/edit. `_film_ids`/`_validate_film_set`/`save_engagement_films`/`_render_engagement_form` signatures match their callers in Tasks 4–5. Alpine `engagementForm()` reads `initial_films` (via `{{ initial_films|json_script:"engagement-initial-films" }}`) and `data-initial-kind` — no JSON is interpolated into an attribute (avoids the double-quote-escaping trap). Hidden `films` inputs (rendered by `x-for`) → `request.POST.getlist("films")` → ordered ids. KIND_LABELS (badge) vs KIND_OPTIONS (form) divergence preserved. `film-selected` detail `{id,title,poster}` matches the sub-project-3 producer and the `addFilm` consumer.
