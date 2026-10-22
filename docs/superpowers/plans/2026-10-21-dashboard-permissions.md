# Dashboard Permissions Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Every dashboard view honours the Django model permission for the object it touches, templates hide controls the user cannot use, and the home page shows only what the user may view.

**Architecture:** `StaffRequiredMixin` gains a `permission_required` attribute and a `has_dashboard_permission()` hook, checked in `dispatch` after the existing staff check. Each view class declares its permission. Templates use Django's `perms` context variable (already provided by the auth context processor) to hide controls. `HomeView` filters cards and alerts by `user.has_perm`. A table-driven test asserts the 403 for every URL, and a guard test asserts every view declares a permission.

**Tech Stack:** Django 5.2, `django.contrib.auth` model permissions, HTMX (`HX-Request` header, `HX-Trigger` toast), Django test runner via `.venv/bin/python manage.py test`.

**Spec:** `docs/superpowers/specs/2026-10-21-dashboard-permissions-design.md`

## Global Constraints

- Test command: `.venv/bin/python manage.py test <dotted path>`; the full suite is `.venv/bin/python manage.py test`. A task is done only when the full suite reports no failures.
- Lint gate: flake8 findings only on added or changed lines (repo baseline is dirty; see `.flake8`). Line length 88.
- No new models, migrations, settings, or preset groups.
- Permission strings are exactly those in the spec's map, `app_label.codename`.
- Non-HTMX denied requests keep today's behaviour: `PermissionDenied` (a plain 403). HTMX denied requests get a 403 response carrying `HX-Trigger` with `{"dashboard-toast": {"kind": "error", "message": "You don't have permission to do that."}}`.
- The server is authoritative: a hidden control's URL still answers 403.
- Commit after each task with the message style used in `git log` (`feat(dashboard): …`, `test(dashboard): …`), ending with `Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>`.

## Review Focus

1. **HTMX request without permission.** A stale tab posts a delete; the user expects a visible error, not a silent no-op. Pinned in Task 1 (`test_htmx_denied_carries_toast`).
2. **Staff user with zero permissions opens home.** Expects a page with the welcome header and nothing else, not a crash on a missing context key. Pinned in Task 12 (`test_no_permissions_renders_header_only`).
3. **Superuser with no explicit permissions.** Expects every sidebar link and every button, since `has_perm` short-circuits. Pinned in Task 11 (`test_superuser_sees_every_link`).
4. **Engagement status dropdown for a user without `change_engagement`.** Expects a static status badge, not a menu whose every item 403s. Pinned in Task 4 (`test_status_badge_static_without_change`).
5. **Engagement detail with `view_engagement` but no showtime or ticket permissions.** Expects the showtime rows with no Add, Edit, Delete buttons and no door-list link. Pinned in Task 4 (`test_detail_hides_showtime_controls`).

---

### Task 1: The access mixin and the test helper

**Files:**
- Modify: `dashboard/mixins.py`
- Create: `dashboard/tests/helpers.py`
- Modify: `dashboard/tests/test_auth.py`

**Interfaces:**
- Produces: `StaffRequiredMixin.permission_required: str | tuple[str, ...] = ()`; `StaffRequiredMixin.has_dashboard_permission(self) -> bool` (default: `self.request.user.has_perms(self.permissions_tuple())`); `StaffRequiredMixin.permissions_tuple(self) -> tuple[str, ...]` (normalises a str to a one-tuple).
- Produces: `dashboard.tests.helpers.ALL` (sentinel object); `DASHBOARD_PERMISSIONS: frozenset[str]` built by walking `dashboard.urls.urlpatterns`, taking `pattern.callback.view_class.permission_required` where present, normalised to a tuple, and unioned; `make_staff(username="staffer", password="pw12345", perms=ALL, **extra) -> User` creating an `is_staff` user holding `DASHBOARD_PERMISSIONS` when `perms is ALL`, else exactly the given iterable of `app.codename` strings (resolved to `Permission` rows via `content_type__app_label` and `codename`); `permissions_except(*codenames) -> set[str]` returning `DASHBOARD_PERMISSIONS` minus the given ones.

- [ ] **Step 1: Write the failing tests in `dashboard/tests/test_auth.py`**

Add two tiny guarded views for the tests, registered through a test-only URLconf (use `@override_settings(ROOT_URLCONF=...)` with a module-level `urlpatterns` in the test file that includes the real `dashboard.urls` plus `path("perm-probe", ProbeView.as_view())` and `path("perm-probe-all", ProbeAllView.as_view())`). `ProbeView(StaffRequiredMixin, View)` has `permission_required = "cinema.view_screen"`, a `get` returning `HttpResponse("ok")` and a `post` returning `HttpResponse("posted")`. `ProbeAllView` is the same with `permission_required = ("cinema.view_screen", "cinema.add_screen")`.

```python
def test_staff_without_permission_forbidden(self):
    make_staff(username="viewer", perms=())
    self.client.login(username="viewer", password="pw12345")
    self.assertEqual(self.client.get("/perm-probe").status_code, 403)

def test_staff_with_permission_ok(self):
    make_staff(username="viewer", perms=("cinema.view_screen",))
    self.client.login(username="viewer", password="pw12345")
    self.assertEqual(self.client.get("/perm-probe").status_code, 200)

def test_superuser_without_explicit_permission_ok(self):
    User.objects.create_superuser(username="root", password="pw12345")
    self.client.login(username="root", password="pw12345")
    self.assertEqual(self.client.get("/perm-probe").status_code, 200)

def test_htmx_denied_carries_toast(self):
    make_staff(username="viewer", perms=())
    self.client.login(username="viewer", password="pw12345")
    resp = self.client.post("/perm-probe", HTTP_HX_REQUEST="true")
    self.assertEqual(resp.status_code, 403)
    trigger = json.loads(resp["HX-Trigger"])
    self.assertEqual(trigger["dashboard-toast"],
                     {"kind": "error", "message": "You don't have permission to do that."})

def test_tuple_requires_every_permission(self):
    # ProbeAllView.permission_required = ("cinema.view_screen", "cinema.add_screen")
    make_staff(username="viewer", perms=("cinema.view_screen",))
    self.client.login(username="viewer", password="pw12345")
    self.assertEqual(self.client.get("/perm-probe-all").status_code, 403)

def test_make_staff_default_holds_every_dashboard_permission(self):
    user = make_staff()
    self.assertTrue(user.has_perm("cinema.view_screen"))
    self.assertTrue(user.has_perm("phone.delete_voicemail"))
```

`DASHBOARD_PERMISSIONS` is empty until later tasks declare permissions, so for the last test to be meaningful in this task, `helpers.py` must also union the probe-independent set from the spec. Do that: define `SPEC_PERMISSIONS` in `helpers.py` as the literal frozenset of every `app.codename` in the spec's map, and `DASHBOARD_PERMISSIONS = SPEC_PERMISSIONS | <declared by views>`. Task 13's guard test then asserts the two sets are equal, which catches a view declaring a permission the spec does not name and vice versa.

- [ ] **Step 2: Run the tests to verify they fail**

Run: `.venv/bin/python manage.py test dashboard.tests.test_auth -v 2`
Expected: FAIL (`ImportError` for `make_staff`, then 200 where 403 expected).

- [ ] **Step 3: Implement the mixin in `dashboard/mixins.py`**

Keep the anonymous and non-staff branches as they are. After them: `if not self.has_dashboard_permission(): return self.permission_denied_response(request)`. `permission_denied_response(self, request) -> HttpResponse`: if `request.headers.get("HX-Request")`, return `HttpResponseForbidden()` with `resp["HX-Trigger"] = json.dumps({...})` using the exact message from Global Constraints; otherwise `raise PermissionDenied`.

- [ ] **Step 4: Implement `dashboard/tests/helpers.py`** with the interface above.

- [ ] **Step 5: Run the tests to verify they pass**

Run: `.venv/bin/python manage.py test dashboard.tests.test_auth -v 2`
Expected: PASS, all cases.

- [ ] **Step 6: Commit**

```bash
git add dashboard/mixins.py dashboard/tests/helpers.py dashboard/tests/test_auth.py
git commit -m "feat(dashboard): StaffRequiredMixin checks a declared permission"
```

---

### Task 2: Move existing tests onto `make_staff()`

**Files:**
- Modify: every file in `dashboard/tests/` that calls `create_user(..., is_staff=True)` (30 files, 67 call sites; find them with `grep -rn "is_staff=True" dashboard/tests`)
- Modify: `blog/tests/test_header_image.py`, `cinema/tests/test_rental_inquiry_status.py`, `web/tests/test_sponsorship_removed.py` (they hit dashboard URLs as staff)

**Interfaces:**
- Consumes: `make_staff(username, password, perms=ALL, **extra)` from Task 1.

- [ ] **Step 1: Replace each staff `create_user` call with `make_staff(...)`**, keeping the same `username`, `password`, and any extra kwargs (`first_name="Bran"` in `test_home.py`). Where a file used `get_user_model()` only for this call, drop the now-unused import. Do not touch non-staff users. Leave `test_auth.py`'s `self.plain` as is.

- [ ] **Step 2: Run the full suite**

Run: `.venv/bin/python manage.py test`
Expected: PASS with the same count as before plus Task 1's new tests. Nothing declares a permission yet, so behaviour is unchanged; this task only proves the helper is a drop-in.

- [ ] **Step 3: Commit**

```bash
git add -A dashboard/tests blog/tests cinema/tests web/tests
git commit -m "test(dashboard): build staff users through make_staff()"
```

---

### Task 3: Permission table test, screens, and films

**Files:**
- Create: `dashboard/tests/test_permission_map.py`
- Modify: `dashboard/views.py` (ScreenListView, ScreenCreateView, ScreenEditView, ScreenDeleteView, FilmSearchView, FilmSearchTMDBView, FilmFromTMDBView)
- Modify: `dashboard/templates/dashboard/screens.html`, `_screen_list.html`, `_film_search_combo.html`
- Modify: `dashboard/tests/test_screens.py`

**Interfaces:**
- Produces: `PERMISSION_TABLE: list[tuple[str, dict, str, str | tuple[str, ...]]]` in `test_permission_map.py`, rows of `(url_name, kwargs, method, permission)`. `permission` is one codename, or a tuple of alternatives for an any-of view. Later tasks append rows. Row `kwargs` use non-existent pks (`{"pk": 999999}`, `{"eng_pk": 999999}`, `{"pk": 999999, "vote_pk": 999999}`, and so on): the permission check runs in `dispatch` before any lookup, so a 403 proves denial and a 404 proves the gate opened.

- [ ] **Step 1: Write `test_permission_map.py`**

`PermissionMapTests(TestCase)` with one test method that loops over `PERMISSION_TABLE` using `self.subTest(url_name=...)`. Per row: build the URL with `reverse(f"dashboard:{url_name}", kwargs=kwargs)`; alternatives = `permission` as a tuple. Deny case: `make_staff(username=f"deny-{i}", perms=permissions_except(*alternatives))`, log in, call `getattr(self.client, method)(url)`, assert status 403. Allow case: `make_staff(username=f"allow-{i}", perms=(alternatives[0],))`, log in, same call, assert status != 403. Log out between users (`self.client.logout()`).

Starting rows:

```python
("screens", {}, "get", "cinema.view_screen"),
("screen_create", {}, "get", "cinema.add_screen"),
("screen_edit", {"pk": 999999}, "get", "cinema.change_screen"),
("screen_delete", {"pk": 999999}, "post", "cinema.delete_screen"),
("film_search", {}, "get", "cinema.view_film"),
("film_search_tmdb", {}, "get", "cinema.add_film"),
("film_from_tmdb", {}, "post", "cinema.add_film"),
```

- [ ] **Step 2: Run it to verify it fails**

Run: `.venv/bin/python manage.py test dashboard.tests.test_permission_map`
Expected: FAIL on every deny case (200 or 404 where 403 expected).

- [ ] **Step 3: Declare `permission_required` on the seven view classes** per the spec map.

- [ ] **Step 4: Run it to verify it passes**

Run: `.venv/bin/python manage.py test dashboard.tests.test_permission_map`
Expected: PASS.

- [ ] **Step 5: Write the template test in `test_screens.py`**

```python
def test_view_only_user_sees_no_controls(self):
    screen = Screen.objects.create(name="Screen 1", capacity=100)
    make_staff(username="viewer", perms=("cinema.view_screen",))
    self.client.login(username="viewer", password="pw12345")
    html = self.client.get(reverse("dashboard:screens")).content.decode()
    self.assertIn("Screen 1", html)
    self.assertNotIn(reverse("dashboard:screen_create"), html)
    self.assertNotIn(reverse("dashboard:screen_edit", args=[screen.pk]), html)
    self.assertNotIn(reverse("dashboard:screen_delete", args=[screen.pk]), html)

def test_add_only_user_sees_new_but_not_edit(self):
    # perms=("cinema.view_screen", "cinema.add_screen"); assert New present, Edit URL absent
```

- [ ] **Step 6: Run to verify it fails**, then wrap the controls:

| Template | Control | Wrap in |
|---|---|---|
| `screens.html` | New Screen button | `perms.cinema.add_screen` |
| `_screen_list.html` | Edit buttons (table and card) | `perms.cinema.change_screen` |
| `_screen_list.html` | Delete buttons (table and card) | `perms.cinema.delete_screen` |
| `_screen_list.html` | empty-state Add First Screen | `perms.cinema.add_screen` |
| `_film_search_combo.html` | the TMDB search input and its results target | `perms.cinema.add_film` |

Leave the Actions `<th>` and `<td>` in place so the table stays aligned.

- [ ] **Step 7: Run `dashboard.tests.test_screens` and `dashboard.tests.test_films`**; Expected: PASS.

- [ ] **Step 8: Commit**

```bash
git add dashboard/views.py dashboard/templates/dashboard dashboard/tests
git commit -m "feat(dashboard): screens and films honour model permissions"
```

---

### Task 4: Engagements, showtimes, social cards

**Files:**
- Modify: `dashboard/views.py` (Engagement*, Showtime*, EngagementSocialCardView)
- Modify: `dashboard/templates/dashboard/engagements.html`, `_engagement_list.html`, `_status_dropdown.html`, `_showtime_section.html`, `_showtime_list.html`
- Modify: `dashboard/tests/test_permission_map.py`, `dashboard/tests/test_engagements.py`, `dashboard/tests/test_engagement_detail.py`

- [ ] **Step 1: Append rows to `PERMISSION_TABLE`**

```python
("engagements", {}, "get", "cinema.view_engagement"),
("engagement_detail", {"pk": 999999}, "get", "cinema.view_engagement"),
("engagement_social_card", {"pk": 999999, "platform": "facebook"}, "get", "cinema.view_engagement"),
("engagement_create", {}, "get", "cinema.add_engagement"),
("engagement_edit", {"pk": 999999}, "get", "cinema.change_engagement"),
("engagement_status", {"pk": 999999}, "post", "cinema.change_engagement"),
("engagement_square_retry", {"pk": 999999}, "post", "cinema.change_engagement"),
("engagement_delete", {"pk": 999999}, "post", "cinema.delete_engagement"),
("showtime_create", {"eng_pk": 999999}, "get", "cinema.add_showtime"),
("showtime_bulk", {"eng_pk": 999999}, "get", "cinema.add_showtime"),
("showtime_edit", {"pk": 999999}, "get", "cinema.change_showtime"),
("showtime_delete", {"pk": 999999}, "post", "cinema.delete_showtime"),
```

- [ ] **Step 2: Run, expect FAIL; declare permissions on the twelve views; run, expect PASS.**

- [ ] **Step 3: Write template tests**

In `test_engagements.py`, with one CONFIRMED engagement in the fixture:

```python
def test_view_only_user_sees_no_controls(self):
    # perms=("cinema.view_engagement",)
    # assert: title present; engagement_create, engagement_edit, engagement_delete URLs absent

def test_status_badge_static_without_change(self):
    # perms=("cinema.view_engagement",)
    # assert: 'class="statusMenu"' absent, engagement_status URL absent, the status label present
```

In `test_engagement_detail.py`, with an engagement that has one showtime:

```python
def test_detail_hides_showtime_controls(self):
    # perms=("cinema.view_engagement",)
    # assert 200; showtime time present; showtime_create, showtime_bulk, showtime_edit,
    # showtime_delete, showtime_orders URLs absent

def test_detail_shows_showtime_controls_with_permissions(self):
    # perms=("cinema.view_engagement", "cinema.add_showtime", "cinema.change_showtime",
    #        "cinema.delete_showtime", "tickets.view_ticketorder")
    # assert all five URLs present
```

- [ ] **Step 4: Run, expect FAIL; wrap the controls**

| Template | Control | Wrap in |
|---|---|---|
| `engagements.html` | New Engagement button | `perms.cinema.add_engagement` |
| `_engagement_list.html` | Edit (table and card) | `perms.cinema.change_engagement` |
| `_engagement_list.html` | Delete (table and card) | `perms.cinema.delete_engagement` |
| `_status_dropdown.html` | the toggle's `@click` and the whole `statusMenu` | `perms.cinema.change_engagement`; without it render the badge `<button>` as `disabled` with no chevron and no menu |
| `_showtime_section.html` | New Showtime, Bulk add | `perms.cinema.add_showtime` |
| `_showtime_list.html` | Edit (table and card) | `perms.cinema.change_showtime` |
| `_showtime_list.html` | Delete (table and card) | `perms.cinema.delete_showtime` |
| `_showtime_list.html` | sold-count link to `showtime_orders` | `perms.tickets.view_ticketorder`; without it print the count as text |
| `_showtime_list.html` | empty-state Add your first showtime | `perms.cinema.add_showtime` |

Social card download buttons share the page's permission; leave them.

- [ ] **Step 5: Run `dashboard.tests.test_engagements dashboard.tests.test_engagement_detail dashboard.tests.test_social_cards`**; Expected: PASS.

- [ ] **Step 6: Commit** `feat(dashboard): engagements and showtimes honour model permissions`

---

### Task 5: Online tickets

**Files:**
- Modify: `dashboard/ticket_views.py` (all eleven view classes)
- Modify: `dashboard/templates/dashboard/showtime_orders.html`, `_allowance_form.html`, `_ticket_order_row.html`, `_ticket_log_row.html`
- Modify: `dashboard/tests/test_permission_map.py`, `dashboard/tests/test_showtime_orders.py`

- [ ] **Step 1: Append rows**

```python
("showtime_orders", {"pk": 999999}, "get", "tickets.view_ticketorder"),
("showtime_orders_export", {"pk": 999999}, "get", "tickets.view_ticketorder"),
("tickets", {}, "get", "tickets.view_ticketorder"),
("ticket_orders", {}, "get", "tickets.view_ticketorder"),
("ticket_orders_export", {}, "get", "tickets.view_ticketorder"),
("showtime_allowance", {"pk": 999999}, "post", "cinema.change_showtime"),
("showtime_refund_all", {"pk": 999999}, "post", "tickets.change_ticketorder"),
("ticket_order_arrive", {"pk": 999999}, "post", "tickets.change_ticketorder"),
("ticket_order_unarrive", {"pk": 999999}, "post", "tickets.change_ticketorder"),
("ticket_order_retry", {"pk": 999999}, "post", "tickets.change_ticketorder"),
("ticket_order_refund", {"pk": 999999}, "post", "tickets.change_ticketorder"),
```

- [ ] **Step 2: Run, expect FAIL; declare; run, expect PASS.**

- [ ] **Step 3: Template test in `test_showtime_orders.py`**, using that file's existing showtime-with-a-paid-order fixture:

```python
def test_view_only_user_sees_door_list_without_actions(self):
    # perms=("tickets.view_ticketorder",)
    # assert 200; order number present; ticket_order_arrive, ticket_order_refund,
    # showtime_allowance, showtime_refund_all URLs absent; the allowance value still printed
```

- [ ] **Step 4: Run, expect FAIL; wrap**

| Template | Control | Wrap in |
|---|---|---|
| `_allowance_form.html` | the form | `perms.cinema.change_showtime`; without it render the current allowance as text in the same spot |
| `showtime_orders.html` | Refund all form | `perms.tickets.change_ticketorder` |
| `_ticket_order_row.html` | retry, arrive, unarrive, refund forms | `perms.tickets.change_ticketorder` |
| `_ticket_log_row.html` | retry, refund forms | `perms.tickets.change_ticketorder` |

- [ ] **Step 5: Run `dashboard.tests.test_showtime_orders dashboard.tests.test_ticket_pages dashboard.tests.test_showtime_allowance dashboard.tests.test_ticket_delete_guards`**; Expected: PASS.

- [ ] **Step 6: Commit** `feat(dashboard): ticket views honour model permissions`

---

### Task 6: Polls

**Files:**
- Modify: `dashboard/poll_views.py`
- Modify: `dashboard/templates/dashboard/polls.html`, `_poll_list.html`, `poll_detail.html`, `_poll_options.html`, `_poll_status.html`, `_poll_voters.html`
- Modify: `dashboard/tests/test_permission_map.py`, `dashboard/tests/test_polls.py`

- [ ] **Step 1: Append rows**

```python
("polls", {}, "get", "cinema.view_poll"),
("poll_detail", {"pk": 999999}, "get", "cinema.view_poll"),
("poll_votes_export", {"pk": 999999}, "get", "cinema.view_poll"),
("poll_create", {}, "get", "cinema.add_poll"),
("poll_edit", {"pk": 999999}, "get", "cinema.change_poll"),
("poll_status", {"pk": 999999}, "post", "cinema.change_poll"),
("poll_announce", {"pk": 999999}, "get", "cinema.change_poll"),
("poll_delete", {"pk": 999999}, "post", "cinema.delete_poll"),
("poll_option_add", {"pk": 999999}, "post", "cinema.add_polloption"),
("poll_option_move", {"pk": 999999, "option_pk": 999999}, "post", "cinema.change_polloption"),
("poll_option_remove", {"pk": 999999, "option_pk": 999999}, "post", "cinema.delete_polloption"),
("poll_vote_remove", {"pk": 999999, "vote_pk": 999999}, "post", "cinema.delete_vote"),
```

- [ ] **Step 2: Run, expect FAIL; declare; run, expect PASS.**

- [ ] **Step 3: Template test in `test_polls.py`**, poll with one option and one vote:

```python
def test_view_only_user_sees_detail_without_controls(self):
    # perms=("cinema.view_poll",)
    # assert 200; poll title present; poll_delete, poll_status, poll_announce,
    # poll_option_move, poll_option_remove, poll_vote_remove URLs absent;
    # 'data-add-url' absent
```

- [ ] **Step 4: Run, expect FAIL; wrap**

| Template | Control | Wrap in |
|---|---|---|
| `polls.html` | New Poll | `perms.cinema.add_poll` |
| `_poll_list.html` | Edit / Delete | `perms.cinema.change_poll` / `perms.cinema.delete_poll` |
| `poll_detail.html` | Delete form | `perms.cinema.delete_poll` |
| `poll_detail.html` | the `pollBallot` add control (`data-add-url` element and its input) | `perms.cinema.add_polloption` |
| `_poll_options.html` | move up/down | `perms.cinema.change_polloption` |
| `_poll_options.html` | remove | `perms.cinema.delete_polloption` |
| `_poll_status.html` | status buttons and Announce | `perms.cinema.change_poll` |
| `_poll_voters.html` | vote remove | `perms.cinema.delete_vote` |

- [ ] **Step 5: Run `dashboard.tests.test_polls dashboard.tests.test_poll_options dashboard.tests.test_poll_status`**; Expected: PASS.

- [ ] **Step 6: Commit** `feat(dashboard): polls honour model permissions`

---

### Task 7: Inquiries and voicemails

**Files:**
- Modify: `dashboard/rental_inquiry_views.py`, `dashboard/ad_inquiry_views.py`, `dashboard/voicemail_views.py`
- Modify: `dashboard/templates/dashboard/rental_inquiries.html`, `ad_inquiries.html`, `voicemails.html`
- Modify: `dashboard/tests/test_permission_map.py`, `dashboard/tests/test_voicemails.py`, `dashboard/tests/test_rental_inquiries.py`

- [ ] **Step 1: Append rows**

```python
("rental_inquiries", {}, "get", "cinema.view_rentalinquiry"),
("rental_inquiry_status", {"pk": 999999}, "post", "cinema.change_rentalinquiry"),
("ad_inquiries", {}, "get", "cinema.view_adinquiry"),
("ad_inquiry_status", {"pk": 999999}, "post", "cinema.change_adinquiry"),
("voicemails", {}, "get", "phone.view_voicemail"),
("voicemail_audio", {"pk": 999999}, "get", "phone.view_voicemail"),
("voicemail_status", {"pk": 999999}, "post", "phone.change_voicemail"),
("voicemail_notes", {"pk": 999999}, "post", "phone.change_voicemail"),
("voicemail_delete", {"pk": 999999}, "post", "phone.delete_voicemail"),
```

- [ ] **Step 2: Run, expect FAIL; declare; run, expect PASS.**

- [ ] **Step 3: Template tests**

`test_voicemails.py`: `test_view_only_user_sees_player_without_forms` with `perms=("phone.view_voicemail",)`: audio URL present; status, notes, delete URLs absent; the status label printed as text.
`test_rental_inquiries.py`: `test_view_only_user_sees_status_as_text` with `perms=("cinema.view_rentalinquiry",)`: inquiry name present; `rental_inquiry_status` URL absent; the status display present.

- [ ] **Step 4: Run, expect FAIL; wrap**

| Template | Control | Wrap in |
|---|---|---|
| `rental_inquiries.html` | status form | `perms.cinema.change_rentalinquiry`; else the status display as text |
| `ad_inquiries.html` | status form | `perms.cinema.change_adinquiry`; else text |
| `voicemails.html` | status form, notes form | `perms.phone.change_voicemail`; else status as text and notes as read-only text |
| `voicemails.html` | delete form | `perms.phone.delete_voicemail` |

- [ ] **Step 5: Run `dashboard.tests.test_voicemails dashboard.tests.test_rental_inquiries dashboard.tests.test_ad_inquiries cinema.tests.test_rental_inquiry_status`**; Expected: PASS.

- [ ] **Step 6: Commit** `feat(dashboard): inquiries and voicemails honour model permissions`

---

### Task 8: Members, terms, free admissions

**Files:**
- Modify: `dashboard/member_views.py`, `dashboard/term_views.py`
- Modify: `dashboard/templates/dashboard/members.html`, `_member_list.html`, `member_detail.html`, `_term_list.html`, `_free_admission_list.html`, `terms.html`
- Modify: `dashboard/tests/test_permission_map.py`, `dashboard/tests/test_members.py`

- [ ] **Step 1: Append rows**

```python
("members", {}, "get", "audience.view_member"),
("member_detail", {"pk": 999999}, "get", "audience.view_member"),
("members_export", {}, "get", "audience.view_member"),
("member_create", {}, "get", "audience.add_member"),
("member_edit", {"pk": 999999}, "get", "audience.change_member"),
("member_delete", {"pk": 999999}, "post", "audience.delete_member"),
("terms", {}, "get", "audience.view_membershipterm"),
("terms_export", {}, "get", "audience.view_membershipterm"),
("term_create", {"pk": 999999}, "get", "audience.add_membershipterm"),
("term_edit", {"pk": 999999}, "get", "audience.change_membershipterm"),
("term_delete", {"pk": 999999}, "post", "audience.delete_membershipterm"),
("free_admission_redeem", {"pk": 999999}, "post", "audience.add_freeadmission"),
("free_admission_delete", {"pk": 999999}, "post", "audience.delete_freeadmission"),
```

- [ ] **Step 2: Run, expect FAIL; declare; run, expect PASS.**

- [ ] **Step 3: Template test in `test_members.py`**, member with one term and one free admission:

`test_view_only_user_sees_member_without_controls` with `perms=("audience.view_member",)`: list page shows the name, no `member_create`, `member_edit`, `member_delete`, `free_admission_redeem`, or `terms` URL; detail page shows the term, no `term_create`, `term_edit`, `term_delete`, `free_admission_delete` URL.

- [ ] **Step 4: Run, expect FAIL; wrap**

| Template | Control | Wrap in |
|---|---|---|
| `members.html` | New Member, empty-state Add | `perms.audience.add_member` |
| `members.html` | Terms sold link | `perms.audience.view_membershipterm` |
| `_member_list.html` | Redeem | `perms.audience.add_freeadmission` |
| `_member_list.html` | Edit / Delete | `perms.audience.change_member` / `perms.audience.delete_member` |
| `_member_list.html` | empty-state Add | `perms.audience.add_member` |
| `member_detail.html` | Renew, New Term | `perms.audience.add_membershipterm` |
| `_term_list.html` | Edit / Delete | `perms.audience.change_membershipterm` / `perms.audience.delete_membershipterm` |
| `_free_admission_list.html` | Delete | `perms.audience.delete_freeadmission` |
| `terms.html` | Tiers link | `perms.audience.view_membershiptier` |
| `terms.html` | member name link | `perms.audience.view_member`; else plain text |

- [ ] **Step 5: Run `dashboard.tests.test_members dashboard.tests.test_member_terms dashboard.tests.test_member_forms dashboard.tests.test_free_admissions dashboard.tests.test_term_ledger dashboard.tests.test_csv_export audience.tests`**; Expected: PASS.

- [ ] **Step 6: Commit** `feat(dashboard): members and terms honour model permissions`

---

### Task 9: Tiers, benefits, Square sales, subscribers

**Files:**
- Modify: `dashboard/tier_views.py`, `dashboard/membership_sale_views.py`, `dashboard/subscriber_views.py`
- Modify: `dashboard/templates/dashboard/tiers.html`, `_tier_list.html`, `_benefit_list.html`, `_square_sale_row.html`, `subscribers.html`
- Modify: `dashboard/tests/test_permission_map.py`, `dashboard/tests/test_tiers.py`

- [ ] **Step 1: Append rows**

```python
("tiers", {}, "get", "audience.view_membershiptier"),
("tier_create", {}, "get", "audience.add_membershiptier"),
("tier_edit", {"pk": 999999}, "get", "audience.change_membershiptier"),
("tier_listing", {"pk": 999999}, "post", "audience.change_membershiptier"),
("tier_delete", {"pk": 999999}, "post", "audience.delete_membershiptier"),
("benefit_create", {}, "get", "audience.add_membershipbenefit"),
("benefit_edit", {"pk": 999999}, "get", "audience.change_membershipbenefit"),
("benefit_delete", {"pk": 999999}, "post", "audience.delete_membershipbenefit"),
("square_sales", {}, "get", "boxoffice.view_membershipsale"),
("square_sale_retry", {"pk": 999999}, "post", "boxoffice.change_membershipsale"),
("subscribers", {}, "get", "audience.view_subscriber"),
("subscribers_export", {}, "get", "audience.view_subscriber"),
```

- [ ] **Step 2: Run, expect FAIL; declare; run, expect PASS.**

- [ ] **Step 3: Template test in `test_tiers.py`**, one tier and one benefit:

`test_view_only_user_sees_catalogue_without_controls` with `perms=("audience.view_membershiptier",)`: tier name present; `tier_create`, `tier_edit`, `tier_listing`, `tier_delete`, `benefit_create`, `benefit_edit`, `benefit_delete`, `square_sales`, `terms` URLs absent.

- [ ] **Step 4: Run, expect FAIL; wrap**

| Template | Control | Wrap in |
|---|---|---|
| `tiers.html` | Square sales link | `perms.boxoffice.view_membershipsale` |
| `tiers.html` | Terms sold link | `perms.audience.view_membershipterm` |
| `tiers.html` | New Tier | `perms.audience.add_membershiptier` |
| `tiers.html` | New Benefit | `perms.audience.add_membershipbenefit` |
| `_tier_list.html` | term count link to `terms` | `perms.audience.view_membershipterm`; else text |
| `_tier_list.html` | Edit, Retire/Restore | `perms.audience.change_membershiptier` |
| `_tier_list.html` | Delete | `perms.audience.delete_membershiptier` |
| `_benefit_list.html` | Edit / Delete | `perms.audience.change_membershipbenefit` / `perms.audience.delete_membershipbenefit` |
| `_square_sale_row.html` | Retry form | `perms.boxoffice.change_membershipsale` |
| `_square_sale_row.html` | member link | `perms.audience.view_member`; else text |

`subscribers.html`'s export shares the page permission; leave it.

- [ ] **Step 5: Run `dashboard.tests.test_tiers dashboard.tests.test_square_sales dashboard.tests.test_subscribers`**; Expected: PASS.

- [ ] **Step 6: Commit** `feat(dashboard): tiers, Square sales, subscribers honour model permissions`

---

### Task 10: Blog

**Files:**
- Modify: `dashboard/blog_views.py`
- Modify: `dashboard/templates/dashboard/blog.html`, `_blog_post_list.html`, `blog_editor.html`, `_blog_author_list.html`, `_blog_category_list.html`
- Modify: `dashboard/tests/test_permission_map.py`, `dashboard/tests/test_blog.py`

**Interfaces:**
- `MarkdownPreviewView.permission_required = ("blog.add_blogpost", "blog.change_blogpost")` and overrides `has_dashboard_permission` to return `any(self.request.user.has_perm(p) for p in self.permissions_tuple())`.

- [ ] **Step 1: Append rows** (the markdown preview row carries a tuple of alternatives)

```python
("blog", {}, "get", "blog.view_blogpost"),
("blog_post_preview", {"pk": UUID_NONE}, "get", "blog.view_blogpost"),
("blog_post_create", {}, "get", "blog.add_blogpost"),
("blog_post_edit", {"pk": UUID_NONE}, "get", "blog.change_blogpost"),
("blog_markdown_preview", {}, "post", ("blog.add_blogpost", "blog.change_blogpost")),
("blog_post_delete", {"pk": UUID_NONE}, "post", "blog.delete_blogpost"),
("blog_author_create", {}, "get", "blog.add_blogauthor"),
("blog_author_edit", {"pk": UUID_NONE}, "get", "blog.change_blogauthor"),
("blog_author_delete", {"pk": UUID_NONE}, "post", "blog.delete_blogauthor"),
("blog_category_create", {}, "get", "blog.add_blogcategory"),
("blog_category_edit", {"pk": UUID_NONE}, "get", "blog.change_blogcategory"),
("blog_category_delete", {"pk": UUID_NONE}, "post", "blog.delete_blogcategory"),
```

with `UUID_NONE = uuid.UUID(int=0)` at module top.

- [ ] **Step 2: Run, expect FAIL; declare (with the any-of override on `MarkdownPreviewView`); run, expect PASS.**

- [ ] **Step 3: Tests in `test_blog.py`**

```python
def test_markdown_preview_accepts_change_alone(self):
    # perms=("blog.change_blogpost",) -> post markdown preview -> status 200
def test_view_only_user_sees_posts_without_controls(self):
    # perms=("blog.view_blogpost",); one post, one author, one category
    # assert post title present as text (not a link to blog_post_edit); blog_post_create,
    # blog_post_edit, blog_post_delete absent; "Authors" panel and "Categories" panel absent
def test_author_panel_needs_its_view_permission(self):
    # perms=("blog.view_blogpost", "blog.view_blogauthor") -> author name present,
    # blog_author_create absent, category panel absent
```

- [ ] **Step 4: Run, expect FAIL; wrap**

| Template | Control | Wrap in |
|---|---|---|
| `blog.html` | New Post | `perms.blog.add_blogpost` |
| `blog.html` | Authors panel (heading, New author, include) | `perms.blog.view_blogauthor`; New author also `perms.blog.add_blogauthor` |
| `blog.html` | Categories panel | `perms.blog.view_blogcategory`; New category also `perms.blog.add_blogcategory` |
| `_blog_post_list.html` | title link to edit, Edit button | `perms.blog.change_blogpost`; else title as text |
| `_blog_post_list.html` | Delete | `perms.blog.delete_blogpost` |
| `_blog_post_list.html` | Write the first post | `perms.blog.add_blogpost` |
| `blog_editor.html` | Preview link | `perms.blog.view_blogpost` |
| `blog_editor.html` | Delete | `perms.blog.delete_blogpost` |
| `_blog_author_list.html` | Edit / Delete | `perms.blog.change_blogauthor` / `perms.blog.delete_blogauthor` |
| `_blog_category_list.html` | Edit / Delete | `perms.blog.change_blogcategory` / `perms.blog.delete_blogcategory` |

- [ ] **Step 5: Run `dashboard.tests.test_blog blog.tests`**; Expected: PASS.

- [ ] **Step 6: Commit** `feat(dashboard): blog honours model permissions`

---

### Task 11: Sidebar and keyboard hint

**Files:**
- Modify: `dashboard/templates/dashboard/_sidebar.html`, `base_dashboard.html`
- Modify: `dashboard/static/dashboard/js/dashboard.js` (Alt+N handler)
- Modify: `dashboard/tests/test_chrome.py`

- [ ] **Step 1: Write the tests in `test_chrome.py`**

```python
def test_sidebar_shows_only_viewable_sections(self):
    make_staff(username="box", perms=("tickets.view_ticketorder",))
    self.client.login(username="box", password="pw12345")
    html = self.client.get(reverse("dashboard:home")).content.decode()
    self.assertIn(reverse("dashboard:tickets"), html)
    for name in ("ad_inquiries", "blog", "engagements", "members", "tiers", "polls",
                 "rental_inquiries", "screens", "subscribers", "voicemails"):
        self.assertNotIn(f'href="{reverse(f"dashboard:{name}")}"', html)
    self.assertNotIn("sidebarBadge", html)
    self.assertNotIn("keyboardHint", html)

def test_superuser_sees_every_link(self):
    # create_superuser, log in, assert every one of the eleven section URLs present and keyboardHint present

def test_keyboard_hint_needs_add_engagement(self):
    # perms=("cinema.add_engagement",) -> keyboardHint present
```

- [ ] **Step 2: Run, expect FAIL; implement**

Wrap each sidebar link per the spec's sidebar table (Home stays unconditional). The voicemail badge and its `new_voicemail_count` call sit inside the Voicemails block, so they come along. Wrap the `keyboardHint` div in `base_dashboard.html` in `perms.cinema.add_engagement`. In `dashboard.js`, make the Alt+N handler return early when `!document.querySelector('.keyboardHint')`.

- [ ] **Step 3: Run `dashboard.tests.test_chrome dashboard.tests.test_static_assets`**; Expected: PASS.

- [ ] **Step 4: Commit** `feat(dashboard): sidebar and Alt+N hint follow view permissions`

---

### Task 12: Home filters by permission

**Files:**
- Modify: `dashboard/smart_alerts.py`, `dashboard/views.py` (HomeView), `dashboard/templates/dashboard/home.html`
- Modify: `dashboard/tests/test_smart_alerts.py`, `dashboard/tests/test_home.py`

**Interfaces:**
- Produces: every dict returned by `build_smart_alerts` carries a `"perm": str` key per the spec's alert table. `HomeView` keeps alerts where `user.has_perm(alert["perm"])`.

- [ ] **Step 1: Tests**

`test_smart_alerts.py`: `test_every_alert_carries_a_perm` builds alerts with every input non-zero (one draft engagement, one ending soon, counts of 1, `square_pull_status="FAILED"`, one nearly-sold-out row, one cancelled row) and asserts each alert has `perm` equal to the spec's value for its id prefix. If existing tests compare whole dicts, update them to include the new key.

`test_home.py`:

```python
def test_no_permissions_renders_header_only(self):
    make_staff(username="none", perms=()); login
    resp = self.client.get(reverse("dashboard:home"))
    self.assertEqual(resp.status_code, 200)
    html = resp.content.decode()
    self.assertIn("Welcome back", html)
    for label in ("Active Engagements", "Today's Showtimes", "Screens", "Yesterday's Sales"):
        self.assertNotIn(label, html)
    self.assertNotIn("alertBanner", html)  # use the actual alerts wrapper class from _alerts.html

def test_box_office_user_sees_tickets_only(self):
    # fixture: a NEW voicemail, a DRAFT engagement, a FAILED ticket order, one showtime today
    # perms=("tickets.view_ticketorder", "cinema.view_showtime")
    # assert: "Today's Showtimes" present, ticket failure alert present,
    #         "new voicemail" absent, "draft" absent, "Active Engagements" absent, "Screens" card absent
```

- [ ] **Step 2: Run, expect FAIL; implement**

In `build_smart_alerts`, add `"perm"` to each dict. In `HomeView.get_context_data`, read `user = self.request.user` first; compute each count only when the user holds the matching `view` permission (pass `0`/`None`/`()` otherwise); filter the returned alerts by `perm`; set `sales_panel` only with `boxoffice.view_salespull` (else `None`, which the template already treats as hidden). No new context flags: `home.html` reads `perms` directly. In `home.html`, wrap the four cards, the showtimes section, and the empty-state link per the spec's home table.

- [ ] **Step 3: Run `dashboard.tests.test_home dashboard.tests.test_smart_alerts web.tests`**; Expected: PASS.

- [ ] **Step 4: Commit** `feat(dashboard): home shows only what the user may view`

---

### Task 13: Guard test, README, full-suite and lint gate

**Files:**
- Modify: `dashboard/tests/test_permission_map.py`
- Modify: `README.md`

- [ ] **Step 1: Add the guard tests**

```python
def test_every_view_but_home_declares_a_permission(self):
    for pattern in dashboard.urls.urlpatterns:
        view_class = pattern.callback.view_class
        with self.subTest(view=view_class.__name__):
            if view_class is HomeView:
                self.assertEqual(view_class.permission_required, ())
            else:
                self.assertTrue(view_class.permission_required)

def test_every_url_is_in_the_table(self):
    names = {p.name for p in dashboard.urls.urlpatterns} - {"home"}
    self.assertEqual(names, {row[0] for row in PERMISSION_TABLE})

def test_declared_permissions_match_the_spec(self):
    # helpers.SPEC_PERMISSIONS == permissions declared by the views (collect the same way helpers does)
```

- [ ] **Step 2: Run `dashboard.tests.test_permission_map`**; Expected: PASS. If a URL is missing from the table, that is a gap in an earlier task: add the row and the declaration.

- [ ] **Step 3: README** — add a section after "Phone line":

```markdown
## Granting dashboard access

A dashboard user needs **Staff status** and the Django permissions for what they
should see and do. The sidebar shows only the sections the user holds a `view`
permission for; Edit, Delete, and action buttons appear only with the matching
`change`, `delete`, or `add` permission. Manage users, groups, and permissions
in Django admin at `/admin/`. Superusers see everything.
```

- [ ] **Step 4: Full suite and lint on changed lines**

Run: `.venv/bin/python manage.py test`
Expected: no failures.

Run: `git diff -U0 main... -- '*.py' | .venv/bin/flake8 --diff` (or filter flake8 output to the changed line numbers)
Expected: no findings on added or changed lines.

- [ ] **Step 5: Commit** `docs(dashboard): how to grant dashboard access; guard every view declares a permission`

Then stop and report. The owner decides when to merge and push (see the audit-fix workflow memory).
