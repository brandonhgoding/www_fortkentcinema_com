# Dashboard Screens Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the stub `/dashboard/screens` with the real, pixel-faithful Screens CRUD page over `cinema.Screen`, plus a reusable Alpine **Drawer** primitive, using Django `ModelForm`s + HTMX.

**Architecture:** A shared drawer shell (Alpine store) whose content region is an HTMX swap target; class-based views return HTML fragments; create/edit post into the drawer and swap the list out-of-band on success (drawer close + toast via `HX-Trigger`); delete confirms through the Foundation Confirm primitive and handles `ProtectedError` with a precise toast. All CSS is a verbatim copy of the leprinceos SPA.

**Tech Stack:** Django 5.2, HTMX + Alpine (vendored), Django `TestCase`.

## Global Constraints

- Source of truth for pixel-perfect CSS/markup: `/Users/bgoding/code/SoftwareMaine/www_leprinceos_com` (`src/pages/Screens.tsx`, `src/pages/Screens.module.css`, `src/components/Drawer.tsx`, `src/components/Drawer.module.css`). Verbatim CSS ports must be exact `cp` copies (classnames unchanged).
- Reuse the Foundation primitives: Confirm (`window.dashboardConfirm({title,message,confirmLabel,variant})→Promise<bool>`) and Toast (`window.dashboardToast(kind,message)`). Do not reinvent them.
- All views use `dashboard.mixins.StaffRequiredMixin` (anon→302 `/login?next=`, non-staff→403).
- Enum display labels must match the leprinceos SPA exactly: screen_type → Standard / IMAX / Dolby Cinema; aspect_ratio → Flat (1.85:1) / Scope (2.39:1) / IMAX 1.90:1 / IMAX 1.43:1; sound_system → **Standard / Dolby Digital / Dolby Atmos** (note: the model's own `sound_system` label for "standard" is "Standard Surround"; the dashboard shows "Standard" — match the SPA, both in the list and the form's select).
- Do NOT modify the `cinema` app (models/admin) or `web/`/`blog/`. Only `dashboard/` files change.
- Tests use `django.test.TestCase`, run with `python manage.py test dashboard`.
- Run from repo root `api_fortkentcinema_com/` with `source .venv/bin/activate`.

---

### Task 1: Drawer primitive + HTMX bridges

**Files:**
- Create: `dashboard/static/dashboard/css/drawer.css` (verbatim copy)
- Create: `dashboard/templates/dashboard/_drawer.html`
- Modify: `dashboard/static/dashboard/js/dashboard.js` (drawer store + `close-drawer`/`dashboard-toast`/`htmx:confirm` bridges + focus-first-input)
- Modify: `dashboard/templates/dashboard/base_dashboard.html` (link drawer.css; include `_drawer.html` once)
- Create: `dashboard/tests/test_drawer.py`

**Interfaces:**
- Produces: Alpine `$store.drawer` with `.show(title)` / `.close()`; a drawer shell with swap targets `#drawer-content` and `#drawer-footer`; response-driven `HX-Trigger` events `close-drawer` and `dashboard-toast` ({kind,message}); an `htmx:confirm` bridge honoring `data-dashboard-confirm` (a JSON object) via `window.dashboardConfirm`.

- [ ] **Step 1: Write the failing test**

Create `dashboard/tests/test_drawer.py`:

```python
from pathlib import Path

from django.conf import settings
from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

User = get_user_model()
CSS_DIR = Path(settings.BASE_DIR) / "dashboard" / "static" / "dashboard" / "css"


class DrawerTests(TestCase):
    def setUp(self) -> None:
        User.objects.create_user(username="s", password="pw12345", is_staff=True)
        self.client.login(username="s", password="pw12345")

    def test_drawer_shell_rendered(self) -> None:
        html = self.client.get(reverse("dashboard:home")).content.decode()
        self.assertIn('id="drawer-content"', html)
        self.assertIn('id="drawer-footer"', html)
        self.assertIn("$store.drawer", html)

    def test_drawer_css_byte_identical(self) -> None:
        src = Path(
            "/Users/bgoding/code/SoftwareMaine/www_leprinceos_com/src/components/Drawer.module.css"
        ).read_bytes()
        self.assertEqual((CSS_DIR / "drawer.css").read_bytes(), src)

    def test_js_has_bridges(self) -> None:
        js = (
            Path(settings.BASE_DIR)
            / "dashboard" / "static" / "dashboard" / "js" / "dashboard.js"
        ).read_text()
        self.assertIn("close-drawer", js)
        self.assertIn("dashboard-toast", js)
        self.assertIn("htmx:confirm", js)
        self.assertIn("Alpine.store('drawer'", js)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python manage.py test dashboard.tests.test_drawer -v 2`
Expected: FAIL — drawer shell/css/bridges absent.

- [ ] **Step 3: Copy the drawer CSS verbatim**

```bash
cp /Users/bgoding/code/SoftwareMaine/www_leprinceos_com/src/components/Drawer.module.css \
   dashboard/static/dashboard/css/drawer.css
```

- [ ] **Step 4: Create the drawer shell template**

`dashboard/templates/dashboard/_drawer.html`:

```html
<div class="overlay" x-show="$store.drawer.open" x-cloak
     @keydown.escape.window="$store.drawer.open && $store.drawer.close()"
     @click="$store.drawer.close()" data-cy="drawer-overlay">
  <div class="drawer md" @click.stop role="dialog" aria-modal="true"
       aria-labelledby="drawer-title" tabindex="-1" data-cy="drawer">
    <div class="header">
      <h2 id="drawer-title" class="title" x-text="$store.drawer.title" data-cy="drawer-title"></h2>
      <button type="button" class="closeButton" @click="$store.drawer.close()"
              aria-label="Close drawer" data-cy="drawer-close">
        <svg width="20" height="20" viewBox="0 0 20 20" fill="none" stroke="currentColor"
             stroke-width="2" stroke-linecap="round"><path d="M5 5l10 10M15 5L5 15"/></svg>
      </button>
    </div>
    <div class="content" id="drawer-content" data-cy="drawer-content"></div>
    <div class="footer" id="drawer-footer" data-cy="drawer-footer"></div>
  </div>
</div>
```

- [ ] **Step 5: Add the drawer store + HTMX bridges to dashboard.js**

Append to `dashboard/static/dashboard/js/dashboard.js`:

```javascript
document.addEventListener('alpine:init', () => {
  Alpine.store('drawer', {
    open: false,
    title: '',
    show(title = '') {
      this.title = title;
      this.open = true;
      document.body.style.overflow = 'hidden';
    },
    close() {
      this.open = false;
      document.body.style.overflow = '';
    },
  });
});

// After a fragment is swapped into the drawer content, focus the first field.
document.body.addEventListener('htmx:afterSwap', (e) => {
  if (e.detail.target && e.detail.target.id === 'drawer-content') {
    const first = e.detail.target.querySelector('input, select, textarea');
    first?.focus();
  }
});

// HX-Trigger bridge: close-drawer + dashboard-toast (kind/message).
document.body.addEventListener('close-drawer', () => window.Alpine?.store('drawer').close());
document.body.addEventListener('dashboard-toast', (e) => {
  const d = e.detail || {};
  if (d.message) window.dashboardToast(d.kind || 'info', d.message);
});

// Themed confirm for HTMX requests: elements with data-dashboard-confirm='{...}'.
document.body.addEventListener('htmx:confirm', (e) => {
  const raw = e.detail.elt.getAttribute('data-dashboard-confirm');
  if (!raw) return; // no custom confirm -> let HTMX proceed normally
  e.preventDefault();
  let opts = {};
  try { opts = JSON.parse(raw); } catch (_) { opts = { title: 'Confirm', message: raw }; }
  window.dashboardConfirm(opts).then((ok) => { if (ok) e.detail.issueRequest(true); });
});
```

- [ ] **Step 6: Wire drawer into base_dashboard.html**

Add the drawer.css link in `<head>` after confirm.css:

```html
    <link rel="stylesheet" href="{% static 'dashboard/css/drawer.css' %}" />
```

Include the drawer shell once inside `.layout`, right after the `_confirm.html` include:

```html
      {% include "dashboard/_drawer.html" %}
```

- [ ] **Step 7: Run tests to verify they pass**

Run: `python manage.py test dashboard.tests.test_drawer -v 2`
Expected: PASS (3 tests). Then `python manage.py test dashboard -v 1` → all green.

- [ ] **Step 8: Commit**

```bash
git add dashboard/
git commit -m "feat(dashboard): shared Alpine Drawer primitive + HTMX toast/confirm bridges"
```

---

### Task 2: Screen form, list view, and list page

**Files:**
- Create: `dashboard/forms.py` (`ScreenForm`)
- Create: `dashboard/static/dashboard/css/screens.css` (verbatim copy)
- Create: `dashboard/templatetags/dashboard_extras.py` (`get_item` filter) — `templatetags/__init__.py` already exists
- Create: `dashboard/templates/dashboard/screens.html`, `dashboard/templates/dashboard/_screen_list.html`
- Modify: `dashboard/views.py` (replace `ScreensStubView` with `ScreenListView`), `dashboard/urls.py`
- Create: `dashboard/tests/test_screens.py`

**Interfaces:**
- Consumes: `cinema.models.Screen`; the Foundation base template + `#screen-list` region.
- Produces: `ScreenForm`; `ScreenListView` at `dashboard:screens`; `_screen_list.html` rendering `#screen-list`; label constants `SCREEN_TYPE_LABELS`, `ASPECT_RATIO_LABELS`, `SOUND_SYSTEM_LABELS` and `get_item` filter used by templates.

- [ ] **Step 1: Write the failing test**

Create `dashboard/tests/test_screens.py`:

```python
from cinema.models import Screen
from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

User = get_user_model()


class ScreenListTests(TestCase):
    def setUp(self) -> None:
        User.objects.create_user(username="s", password="pw12345", is_staff=True)
        self.client.login(username="s", password="pw12345")

    def test_empty_state(self) -> None:
        html = self.client.get(reverse("dashboard:screens")).content.decode()
        self.assertIn("empty-state", html)
        self.assertIn("No Screens Configured", html)

    def test_rows_and_labels(self) -> None:
        Screen.objects.create(
            name="Screen 1", capacity=150, screen_type="dolby_cinema",
            aspect_ratio="scope", sound_system="standard", supports_3d=True,
        )
        html = self.client.get(reverse("dashboard:screens")).content.decode()
        self.assertIn("Screen 1", html)
        self.assertIn("150 seats", html)
        self.assertIn("Dolby Cinema", html)          # screen_type label
        self.assertIn("Scope (2.39:1)", html)        # aspect_ratio label
        self.assertIn("Standard", html)              # sound label (NOT "Standard Surround")
        self.assertNotIn("Standard Surround", html)
        self.assertIn("badge3d", html)               # 3D badge present

    def test_requires_staff(self) -> None:
        self.client.logout()
        self.assertEqual(self.client.get(reverse("dashboard:screens")).status_code, 302)
        User.objects.create_user(username="p", password="pw12345", is_staff=False)
        self.client.login(username="p", password="pw12345")
        self.assertEqual(self.client.get(reverse("dashboard:screens")).status_code, 403)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python manage.py test dashboard.tests.test_screens -v 2`
Expected: FAIL — real screens view/templates absent (stub renders "Coming soon").

- [ ] **Step 3: Create the ScreenForm**

`dashboard/forms.py`:

```python
from cinema.models import Screen
from django import forms

# Labels match the leprinceos SPA (note: "standard" sound shows "Standard",
# not the model's "Standard Surround").
SOUND_SYSTEM_CHOICES = [
    ("standard", "Standard"),
    ("dolby_digital", "Dolby Digital"),
    ("dolby_atmos", "Dolby Atmos"),
]


class ScreenForm(forms.ModelForm):
    sound_system = forms.ChoiceField(
        choices=SOUND_SYSTEM_CHOICES,
        widget=forms.Select(attrs={"class": "input"}),
    )

    class Meta:
        model = Screen
        fields = [
            "name", "capacity", "screen_type", "aspect_ratio",
            "sound_system", "supports_3d",
        ]
        widgets = {
            "name": forms.TextInput(
                attrs={"class": "input", "placeholder": "e.g., Screen 1, Main Auditorium"}
            ),
            "capacity": forms.NumberInput(
                attrs={"class": "input", "min": "1", "placeholder": "e.g., 150"}
            ),
            "screen_type": forms.Select(attrs={"class": "input"}),
            "aspect_ratio": forms.Select(attrs={"class": "input"}),
        }
```

- [ ] **Step 4: Copy the screens CSS verbatim**

```bash
cp /Users/bgoding/code/SoftwareMaine/www_leprinceos_com/src/pages/Screens.module.css \
   dashboard/static/dashboard/css/screens.css
```

- [ ] **Step 5: Create the get_item filter**

`dashboard/templatetags/dashboard_extras.py`:

```python
from django import template

register = template.Library()


@register.filter
def get_item(mapping, key):
    """Dict lookup by a variable key in templates: {{ LABELS|get_item:value }}."""
    try:
        return mapping.get(key, key)
    except AttributeError:
        return key
```

- [ ] **Step 6: Create the list region partial**

`dashboard/templates/dashboard/_screen_list.html`:

```html
{% load static dashboard_extras %}
<div id="screen-list">
  {% if screens %}
  <div class="tableWrapper">
    <table class="table">
      <thead>
        <tr><th>Name</th><th>Capacity</th><th>Type</th><th>Aspect Ratio</th><th>Sound</th><th>3D</th><th>Actions</th></tr>
      </thead>
      <tbody>
        {% for screen in screens %}
        <tr>
          <td class="screenName">{{ screen.name }}</td>
          <td>{{ screen.capacity }} seats</td>
          <td><span class="typeBadge type{{ screen.screen_type }}">{{ SCREEN_TYPE_LABELS|get_item:screen.screen_type }}</span></td>
          <td>{{ ASPECT_RATIO_LABELS|get_item:screen.aspect_ratio }}</td>
          <td>{{ SOUND_SYSTEM_LABELS|get_item:screen.sound_system }}</td>
          <td>{% if screen.supports_3d %}<span class="badge3d">3D</span>{% else %}<span class="badgeNo">—</span>{% endif %}</td>
          <td>
            <div class="actions">
              <button class="actionButton" hx-get="{% url 'dashboard:screen_edit' screen.pk %}"
                      hx-target="#drawer-content" @click="$store.drawer.show('Edit Screen')">Edit</button>
              <button class="actionButton deleteButton"
                      hx-post="{% url 'dashboard:screen_delete' screen.pk %}"
                      hx-target="#screen-list" hx-swap="outerHTML"
                      data-dashboard-confirm='{"title":"Delete Screen","message":"Are you sure you want to delete \"{{ screen.name|escapejs }}\"? This may affect existing engagements and showtimes.","confirmLabel":"Delete","variant":"danger"}'>Delete</button>
            </div>
          </td>
        </tr>
        {% endfor %}
      </tbody>
    </table>
  </div>

  <div class="cardList">
    {% for screen in screens %}
    <div class="card">
      <div class="cardHeader">
        <div class="cardTitleRow">
          <h3 class="cardTitle">{{ screen.name }}</h3>
          <span class="typeBadge type{{ screen.screen_type }}">{{ SCREEN_TYPE_LABELS|get_item:screen.screen_type }}</span>
        </div>
        <div class="cardBadges">
          <span class="cardCapacity">{{ screen.capacity }} seats</span>
          {% if screen.supports_3d %}<span class="badge3d">3D</span>{% endif %}
        </div>
      </div>
      <div class="cardBody">
        <div class="cardDetail"><span class="cardLabel">Aspect Ratio</span><span class="cardValue">{{ ASPECT_RATIO_LABELS|get_item:screen.aspect_ratio }}</span></div>
        <div class="cardDetail"><span class="cardLabel">Sound</span><span class="cardValue">{{ SOUND_SYSTEM_LABELS|get_item:screen.sound_system }}</span></div>
      </div>
      <div class="cardActions">
        <button class="actionButton" hx-get="{% url 'dashboard:screen_edit' screen.pk %}"
                hx-target="#drawer-content" @click="$store.drawer.show('Edit Screen')">Edit</button>
        <button class="actionButton deleteButton"
                hx-post="{% url 'dashboard:screen_delete' screen.pk %}"
                hx-target="#screen-list" hx-swap="outerHTML"
                data-dashboard-confirm='{"title":"Delete Screen","message":"Are you sure you want to delete \"{{ screen.name|escapejs }}\"? This may affect existing engagements and showtimes.","confirmLabel":"Delete","variant":"danger"}'>Delete</button>
      </div>
    </div>
    {% endfor %}
  </div>
  {% else %}
  <div class="empty-state">
    <div class="empty-state-icon" style="font-size: 2.5rem;">🎭</div>
    <h3 class="empty-state-title">No Screens Configured</h3>
    <p class="empty-state-description">Define your cinema's auditoriums and screens to begin scheduling engagements and showtimes. Each screen can have unique technical specifications.</p>
    <button class="btn btn-primary" hx-get="{% url 'dashboard:screen_create' %}"
            hx-target="#drawer-content" @click="$store.drawer.show('New Screen')">Add First Screen</button>
  </div>
  {% endif %}
</div>
```

- [ ] **Step 7: Create the page template**

`dashboard/templates/dashboard/screens.html`:

```html
{% extends "dashboard/base_dashboard.html" %}
{% block title %}Screens · LeprinceOS{% endblock %}
{% block content %}
<div class="page">
  <div class="header">
    <div>
      <h1 class="title">Screens</h1>
      <p class="subtitle">Manage your cinema's screens and auditoriums.</p>
    </div>
    <button class="primaryButton" hx-get="{% url 'dashboard:screen_create' %}"
            hx-target="#drawer-content" @click="$store.drawer.show('New Screen')">+ New Screen</button>
  </div>
  {% include "dashboard/_screen_list.html" %}
</div>
{% endblock %}
```

- [ ] **Step 8: Replace the stub view and add label constants**

In `dashboard/views.py`, remove `ScreensStubView` and add:

```python
from cinema.models import Screen

SCREEN_TYPE_LABELS = {"standard": "Standard", "imax": "IMAX", "dolby_cinema": "Dolby Cinema"}
ASPECT_RATIO_LABELS = {
    "flat": "Flat (1.85:1)", "scope": "Scope (2.39:1)",
    "imax_190": "IMAX 1.90:1", "imax_143": "IMAX 1.43:1",
}
SOUND_SYSTEM_LABELS = {"standard": "Standard", "dolby_digital": "Dolby Digital", "dolby_atmos": "Dolby Atmos"}


def screen_labels() -> dict:
    return {
        "SCREEN_TYPE_LABELS": SCREEN_TYPE_LABELS,
        "ASPECT_RATIO_LABELS": ASPECT_RATIO_LABELS,
        "SOUND_SYSTEM_LABELS": SOUND_SYSTEM_LABELS,
    }


class ScreenListView(StaffRequiredMixin, TemplateView):
    template_name = "dashboard/screens.html"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["screens"] = Screen.objects.all()
        ctx.update(screen_labels())
        return ctx
```

In `dashboard/urls.py`, change the `screens` route to the real view:

```python
    path("screens", views.ScreenListView.as_view(), name="screens"),
```

(Keep `EngagementsStubView` as-is for now.)

- [ ] **Step 9: Run tests to verify they pass**

Run: `python manage.py test dashboard.tests.test_screens -v 2`
Expected: PASS (3 tests). (`screen_create`/`screen_edit`/`screen_delete` URLs are referenced in the template but added in Tasks 3–4; to keep this task self-contained, they must resolve now — so add placeholder routes in `urls.py` pointing at stub views in this task, OR implement Task 3–4 routes here. Simplest: add the three routes now pointing at the real views built in Tasks 3–4. Since those views don't exist yet this task, temporarily point them at `ScreenListView` and replace in Tasks 3–4.)

Add to `dashboard/urls.py` in THIS task (temporary targets, finalized in Tasks 3–4):

```python
    path("screens/new", views.ScreenListView.as_view(), name="screen_create"),
    path("screens/<int:pk>/edit", views.ScreenListView.as_view(), name="screen_edit"),
    path("screens/<int:pk>/delete", views.ScreenListView.as_view(), name="screen_delete"),
```

Re-run the tests; expected PASS.

- [ ] **Step 10: Commit**

```bash
git add dashboard/
git commit -m "feat(dashboard): Screens list page (table + mobile cards + empty state)"
```

---

### Task 3: Create / Edit via drawer

**Files:**
- Create: `dashboard/templates/dashboard/_screen_form.html`
- Modify: `dashboard/views.py` (`ScreenCreateView`, `ScreenEditView`), `dashboard/urls.py` (point `screen_create`/`screen_edit` at them)
- Modify: `dashboard/tests/test_screens.py` (create/edit tests)

**Interfaces:**
- Consumes: `ScreenForm`, `#drawer-content`/`#drawer-footer`, `_screen_list.html`, the `close-drawer`/`dashboard-toast` HX-Trigger events.
- Produces: `_screen_form.html` (form → `#drawer-content`, footer buttons → `#drawer-footer` OOB); `dashboard:screen_create` (GET form / POST create), `dashboard:screen_edit` (GET prefilled / POST update).

- [ ] **Step 1: Write the failing test**

Append to `dashboard/tests/test_screens.py`:

```python
import json


class ScreenCreateEditTests(TestCase):
    def setUp(self) -> None:
        User.objects.create_user(username="s", password="pw12345", is_staff=True)
        self.client.login(username="s", password="pw12345")

    def test_get_create_form(self) -> None:
        html = self.client.get(reverse("dashboard:screen_create")).content.decode()
        self.assertIn('id="screen-form"', html)
        self.assertIn("Create Screen", html)  # footer submit label

    def test_post_create_valid(self) -> None:
        resp = self.client.post(
            reverse("dashboard:screen_create"),
            {"name": "Main", "capacity": 200, "screen_type": "standard",
             "aspect_ratio": "flat", "sound_system": "standard", "supports_3d": ""},
        )
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(Screen.objects.filter(name="Main").exists())
        self.assertIn('id="screen-list"', resp.content.decode())  # OOB list swap
        self.assertIn("close-drawer", resp["HX-Trigger"])
        self.assertIn("dashboard-toast", resp["HX-Trigger"])

    def test_post_create_invalid_shows_errors(self) -> None:
        resp = self.client.post(
            reverse("dashboard:screen_create"),
            {"name": "", "capacity": 0, "screen_type": "standard",
             "aspect_ratio": "flat", "sound_system": "standard"},
        )
        self.assertEqual(resp.status_code, 200)
        self.assertIn('id="screen-form"', resp.content.decode())
        self.assertNotIn("HX-Trigger", resp)  # drawer stays open, no close
        self.assertEqual(Screen.objects.count(), 0)

    def test_get_edit_prefilled(self) -> None:
        s = Screen.objects.create(name="Edit Me", capacity=99, screen_type="imax",
                                  aspect_ratio="scope", sound_system="dolby_atmos", supports_3d=True)
        html = self.client.get(reverse("dashboard:screen_edit", args=[s.pk])).content.decode()
        self.assertIn("Edit Me", html)
        self.assertIn("Save Changes", html)  # footer submit label for edit

    def test_post_edit_updates(self) -> None:
        s = Screen.objects.create(name="Old", capacity=50, screen_type="standard",
                                  aspect_ratio="flat", sound_system="standard", supports_3d=False)
        resp = self.client.post(
            reverse("dashboard:screen_edit", args=[s.pk]),
            {"name": "New", "capacity": 75, "screen_type": "standard",
             "aspect_ratio": "flat", "sound_system": "standard", "supports_3d": "on"},
        )
        self.assertEqual(resp.status_code, 200)
        s.refresh_from_db()
        self.assertEqual(s.name, "New")
        self.assertTrue(s.supports_3d)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python manage.py test dashboard.tests.test_screens.ScreenCreateEditTests -v 2`
Expected: FAIL — create/edit views not implemented (routes still point at the list view).

- [ ] **Step 3: Create the form fragment**

`dashboard/templates/dashboard/_screen_form.html`:

```html
<form id="screen-form" class="form" hx-post="{{ form_action }}" hx-target="#drawer-content" hx-swap="innerHTML">
  {% csrf_token %}
  {% if form.non_field_errors %}<div class="login-error">{{ form.non_field_errors }}</div>{% endif %}
  <div class="formRow">
    <div class="formGroup">
      <label for="{{ form.name.id_for_label }}">Screen Name</label>
      {{ form.name }}
      {% if form.name.errors %}<div class="login-error">{{ form.name.errors|striptags }}</div>{% endif %}
    </div>
    <div class="formGroup">
      <label for="{{ form.capacity.id_for_label }}">Capacity (seats)</label>
      {{ form.capacity }}
      {% if form.capacity.errors %}<div class="login-error">{{ form.capacity.errors|striptags }}</div>{% endif %}
    </div>
  </div>
  <div class="formRow">
    <div class="formGroup">
      <label for="{{ form.screen_type.id_for_label }}">Screen Type</label>
      {{ form.screen_type }}
    </div>
    <div class="formGroup">
      <label for="{{ form.aspect_ratio.id_for_label }}">Aspect Ratio</label>
      {{ form.aspect_ratio }}
    </div>
  </div>
  <div class="formRow">
    <div class="formGroup">
      <label for="{{ form.sound_system.id_for_label }}">Sound System</label>
      {{ form.sound_system }}
    </div>
    <div class="formGroup">
      <label class="checkboxLabel">{{ form.supports_3d }} Supports 3D Projection</label>
    </div>
  </div>
</form>
<div id="drawer-footer" class="footer" hx-swap-oob="true">
  <button type="button" class="cancelButton" @click="$store.drawer.close()">Cancel</button>
  <button type="submit" form="screen-form" class="submitButton">{{ submit_label }}</button>
</div>
```

- [ ] **Step 4: Implement the create/edit views**

In `dashboard/views.py` add (imports: `from django.http import HttpResponse`; `from django.shortcuts import get_object_or_404, render`; `from django.urls import reverse`; `import json`; `from .forms import ScreenForm`):

```python
def _render_screen_form(request, form, action_url, submit_label):
    return render(request, "dashboard/_screen_form.html",
                  {"form": form, "form_action": action_url, "submit_label": submit_label})


def _screen_list_response(request, toast_message):
    """Success response: OOB-swap the list, close the drawer, and toast."""
    html = render(request, "dashboard/_screen_list.html",
                  {"screens": Screen.objects.all(), **screen_labels()}).content.decode()
    # mark the list for out-of-band swap so it replaces #screen-list on the page
    html = html.replace('<div id="screen-list">', '<div id="screen-list" hx-swap-oob="true">', 1)
    resp = HttpResponse(html)
    resp["HX-Trigger"] = json.dumps({
        "close-drawer": True,
        "dashboard-toast": {"kind": "success", "message": toast_message},
    })
    return resp


class ScreenCreateView(StaffRequiredMixin, View):
    def get(self, request):
        return _render_screen_form(request, ScreenForm(),
                                   reverse("dashboard:screen_create"), "Create Screen")

    def post(self, request):
        form = ScreenForm(request.POST)
        if form.is_valid():
            form.save()
            return _screen_list_response(request, "Screen created")
        return _render_screen_form(request, form,
                                   reverse("dashboard:screen_create"), "Create Screen")


class ScreenEditView(StaffRequiredMixin, View):
    def get(self, request, pk):
        screen = get_object_or_404(Screen, pk=pk)
        return _render_screen_form(request, ScreenForm(instance=screen),
                                   reverse("dashboard:screen_edit", args=[pk]), "Save Changes")

    def post(self, request, pk):
        screen = get_object_or_404(Screen, pk=pk)
        form = ScreenForm(request.POST, instance=screen)
        if form.is_valid():
            form.save()
            return _screen_list_response(request, "Screen updated")
        return _render_screen_form(request, form,
                                   reverse("dashboard:screen_edit", args=[pk]), "Save Changes")
```

Add `from django.views.generic import View, TemplateView` (View is new).

Point the routes at the real views in `dashboard/urls.py`:

```python
    path("screens/new", views.ScreenCreateView.as_view(), name="screen_create"),
    path("screens/<int:pk>/edit", views.ScreenEditView.as_view(), name="screen_edit"),
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `python manage.py test dashboard.tests.test_screens.ScreenCreateEditTests -v 2`
Expected: PASS (5 tests). Then `python manage.py test dashboard` → all green.

- [ ] **Step 6: Commit**

```bash
git add dashboard/
git commit -m "feat(dashboard): create/edit Screen via drawer form (HTMX)"
```

---

### Task 4: Delete with ProtectedError handling

**Files:**
- Modify: `dashboard/views.py` (`ScreenDeleteView`), `dashboard/urls.py` (point `screen_delete` at it)
- Modify: `dashboard/tests/test_screens.py` (delete tests)

**Interfaces:**
- Consumes: `Screen`; `Engagement`/`Showtime` (to construct the protected-use count); `_screen_list.html`; the `dashboard-toast` event.
- Produces: `dashboard:screen_delete` (POST) — deletes an unreferenced screen (returns refreshed list + success toast); on `ProtectedError` returns the unchanged list + an error toast and does not delete.

- [ ] **Step 1: Write the failing test**

Append to `dashboard/tests/test_screens.py`:

```python
import datetime

from cinema.models import Engagement, Showtime


class ScreenDeleteTests(TestCase):
    def setUp(self) -> None:
        User.objects.create_user(username="s", password="pw12345", is_staff=True)
        self.client.login(username="s", password="pw12345")

    def test_delete_unreferenced(self) -> None:
        s = Screen.objects.create(name="Trash", capacity=10, screen_type="standard",
                                  aspect_ratio="flat", sound_system="standard", supports_3d=False)
        resp = self.client.post(reverse("dashboard:screen_delete", args=[s.pk]))
        self.assertEqual(resp.status_code, 200)
        self.assertFalse(Screen.objects.filter(pk=s.pk).exists())
        self.assertIn("dashboard-toast", resp["HX-Trigger"])

    def test_delete_protected(self) -> None:
        s = Screen.objects.create(name="Busy", capacity=100, screen_type="standard",
                                  aspect_ratio="flat", sound_system="standard", supports_3d=False)
        Engagement.objects.create(screen=s, start_date=datetime.date(2026, 7, 1),
                                  end_date=datetime.date(2026, 7, 7))
        resp = self.client.post(reverse("dashboard:screen_delete", args=[s.pk]))
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(Screen.objects.filter(pk=s.pk).exists())  # NOT deleted
        trigger = resp["HX-Trigger"]
        self.assertIn("dashboard-toast", trigger)
        self.assertIn("Can't delete", trigger)
        self.assertIn("engagement", trigger)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python manage.py test dashboard.tests.test_screens.ScreenDeleteTests -v 2`
Expected: FAIL — delete view routes to the list view (no delete behavior).

- [ ] **Step 3: Implement the delete view**

In `dashboard/views.py` add (import `from django.db.models import ProtectedError`):

```python
class ScreenDeleteView(StaffRequiredMixin, View):
    def post(self, request, pk):
        screen = get_object_or_404(Screen, pk=pk)
        name = screen.name
        try:
            screen.delete()
        except ProtectedError:
            eng = screen.engagements.count()
            shows = screen.showtimes.count()
            msg = (
                f"Can't delete \"{name}\" — it's used by "
                f"{eng} engagement(s) and {shows} showtime(s)."
            )
            return _screen_list_response_error(request, msg)
        return _screen_list_response(request, "Screen deleted")
```

Add the error-response helper next to `_screen_list_response`:

```python
def _screen_list_response_error(request, message):
    """Re-render the (unchanged) list OOB and fire an error toast; keep the row."""
    html = render(request, "dashboard/_screen_list.html",
                  {"screens": Screen.objects.all(), **screen_labels()}).content.decode()
    html = html.replace('<div id="screen-list">', '<div id="screen-list" hx-swap-oob="true">', 1)
    resp = HttpResponse(html)
    resp["HX-Trigger"] = json.dumps({"dashboard-toast": {"kind": "error", "message": message}})
    return resp
```

Point the route at the real view in `dashboard/urls.py`:

```python
    path("screens/<int:pk>/delete", views.ScreenDeleteView.as_view(), name="screen_delete"),
```

Note: `screen.engagements` / `screen.showtimes` are the `related_name`s defined on `Engagement.screen` / `Showtime.screen` in the `cinema` models.

- [ ] **Step 4: Run tests to verify they pass**

Run: `python manage.py test dashboard.tests.test_screens.ScreenDeleteTests -v 2`
Expected: PASS (2 tests). Then `python manage.py test dashboard` → all green.

- [ ] **Step 5: Commit**

```bash
git add dashboard/
git commit -m "feat(dashboard): delete Screen with ProtectedError-aware toast"
```

---

### Task 5: Final verification

**Files:** none (verification only).

- [ ] **Step 1: System + migration checks**

Run: `python manage.py check` → `System check identified no issues`.
Run: `python manage.py makemigrations --check --dry-run` → `No changes detected` (no model changes).

- [ ] **Step 2: Full dashboard suite**

Run: `python manage.py test dashboard -v 2`
Expected: PASS (drawer + screens list/create/edit/delete + all Foundation tests).

- [ ] **Step 3: Whole project suite (no regressions)**

Run: `python manage.py test`
Expected: PASS — `web`/`blog`/`cinema` + all dashboard tests.

- [ ] **Step 4: Manual browser smoke (recommended)**

`runserver`, log in as staff, open `/dashboard/screens`: create a screen via the drawer (verify focus lands on the name field, validation errors show inline, success closes the drawer + toasts + the row appears); edit it; delete an unused screen (themed confirm → row gone + toast); create an Engagement in `/admin` on that screen then try to delete it (precise "Can't delete … used by 1 engagement(s)…" toast, row stays). Compare pixels with the React Screens page (`www_leprinceos_com` `npm run dev`).

---

## Self-Review

**Spec coverage:**
- Shared Drawer primitive (Alpine + verbatim CSS, HX bridges) → Task 1. ✅
- ScreenForm (with sound_system label override) → Task 2. ✅
- List page (table + mobile cards + empty state, verbatim CSS, exact labels) → Task 2. ✅
- HTMX create/edit (drawer form, OOB list swap, close+toast triggers, inline errors) → Task 3. ✅
- Delete + confirm + ProtectedError precise toast → Task 4. ✅
- Views/routing replacing the stub → Tasks 2–4. ✅
- Tests (list/empty/labels/auth, create valid+invalid, edit, delete unreferenced+protected) → Tasks 2–4. ✅
- Reuse Foundation Toast/Confirm; only dashboard/ changed → enforced by Global Constraints. ✅

**Placeholder scan:** No vague steps; all templates/JS/views inlined; the two CSS files are exact `cp` from named sources. Task 2 Step 9 intentionally adds temporary routes (pointed at the list view) so the list template's `{% url %}` calls resolve before Tasks 3–4 replace them with the real views — this is called out explicitly, not a placeholder.

**Type consistency:** `_screen_list_response`/`_screen_list_response_error` both OOB-mark `#screen-list` and set `HX-Trigger`; the create/edit/delete tests assert those exact trigger keys. `screen_labels()` supplies `SCREEN_TYPE_LABELS`/`ASPECT_RATIO_LABELS`/`SOUND_SYSTEM_LABELS` consumed by `_screen_list.html` via `get_item`. `form_action`/`submit_label` context keys match between the views and `_screen_form.html`. Drawer store `$store.drawer.show/close`, `#drawer-content`/`#drawer-footer`, and the `close-drawer`/`dashboard-toast`/`htmx:confirm` bridges are defined in Task 1 and consumed in Tasks 2–4.
