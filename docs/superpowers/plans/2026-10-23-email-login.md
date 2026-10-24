# Email Login Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace Django's built-in `User` with a project-owned `accounts.User` whose email is the login (unique, case-insensitive) and which has no username, for staff and future members alike.

**Architecture:** A new `accounts` app owns `User(AbstractUser)` on the existing `auth_user` table. `accounts 0001` mirrors today's `auth.User` exactly; `accounts 0002` normalises emails, moves the user content type, drops `username` and adds a `Lower(email)` unique constraint. Existing databases are adopted automatically by an `accounts`-provided `migrate` command that records 0001 as applied before Django's consistency check runs.

**Tech Stack:** Django 5.2.3, Python 3.12, SQLite (dev/test), Postgres (prod), django-axes 8.0.0. Tests run with `python manage.py test` (Django `TestCase`).

**Spec:** `docs/superpowers/specs/2026-10-23-email-login-design.md`

## Global Constraints

- Work on branch `feat/email-login` off `main`. Commit per task on the branch; never merge or push (the owner says when).
- `AUTH_USER_MODEL = "accounts.User"`; `User.Meta.db_table = "auth_user"`.
- Constraint name: `accounts_user_email_ci_unique`, on `Lower("email")`.
- Emails are stored stripped and lowercased.
- Login copy: label "Email", error "Invalid email or password."
- Adopt message, exactly: `Adopted the existing auth_user table as accounts.0001_initial.`
- `AXES_LOCKOUT_PARAMETERS` stays `[["username", "ip_address"]]`; the POST field stays named `username`.
- Lint gate: no new flake8 findings on lines the branch adds or changes (repo baseline is dirty; filter `flake8 --extend-exclude=.venv` output by `git diff -U0 main` line numbers).
- Done = full `python manage.py test` green with zero failures.

## Review Focus

1. **Mixed-case email at login** (`Staff@Example.com` for `staff@example.com`): should sign in. Pinned in Task 3 (`test_login_ignores_email_case`) and Task 5.
2. **Email with surrounding spaces typed into admin or the login form**: should be stored/compared trimmed. Pinned in Task 3 (`test_save_strips_and_lowercases_email`) and Task 5 (`test_lockout_username_strips_and_lowercases`).
3. **Existing database where `migrate` is run with `--database` or by `rollback.yml --fake`**: adoption must use the named database and still be a no-op once adopted. Pinned in Task 1 (`test_migrate_adopts_on_named_database`).
4. **Two staff whose emails differ only by case already in a database**: 0002 must refuse and change nothing, naming the user ids. Pinned in Task 4.
5. **A group holding `change_user`** survives the switch and still grants it. Pinned in Task 4 (`test_group_permission_survives_content_type_move`).

---

### Task 1: `accounts` app, mirrored user model, adopt-on-migrate

**Files:**
- Create: `accounts/__init__.py`, `accounts/apps.py`, `accounts/models.py`, `accounts/admin.py`, `accounts/adopt.py`, `accounts/management/__init__.py`, `accounts/management/commands/__init__.py`, `accounts/management/commands/migrate.py`, `accounts/migrations/__init__.py`, `accounts/migrations/0001_initial.py`, `accounts/tests/__init__.py`, `accounts/tests/test_adopt.py`
- Modify: `fortkentcinema/settings.py` (`INSTALLED_APPS`: add `"accounts.apps.AccountsConfig"` **before** `"django.contrib.admin"` so its `migrate` command wins; add `AUTH_USER_MODEL = "accounts.User"` next to `LOGIN_URL`)

**Interfaces:**
- Produces: `accounts.models.User` (at this task: `class User(AbstractUser)` with `Meta.db_table = "auth_user"` and nothing else — still has `username`); `accounts.adopt.adopt_auth_user(connection) -> bool`.

- [ ] **Step 1: Branch.** `git switch -c feat/email-login`

- [ ] **Step 2: Create the app and model, then generate 0001.** `AccountsConfig(name="accounts", default_auto_field="django.db.models.AutoField")` — `AutoField`, because `auth_user.id` is a 32-bit serial and the migration must match the existing column. Model: `class User(AbstractUser)` with `class Meta: db_table = "auth_user"` (no `swappable`; that belongs to `auth.User` only). Admin: `admin.site.register(User, UserAdmin)` with Django's stock `UserAdmin` (replaced in Task 3). Run `python manage.py makemigrations accounts` and confirm `0001_initial.py` creates `User` with `db_table: "auth_user"`, the `groups`/`user_permissions` M2Ms, and depends on `("auth", "0012_alter_user_first_name_max_length")`.

- [ ] **Step 3: Write the failing adopt tests** in `accounts/tests/test_adopt.py` (`TestCase`; use `MigrationRecorder(connection)` and `recorder.migration_qs.filter(app="accounts", name="0001_initial")`):

```python
def test_records_0001_when_auth_user_exists_and_row_missing(self):
    self.row().delete()
    self.assertTrue(adopt_auth_user(connection))
    self.assertTrue(self.row().exists())

def test_second_call_changes_nothing(self):
    self.row().delete()
    adopt_auth_user(connection)
    self.assertFalse(adopt_auth_user(connection))
    self.assertEqual(self.row().count(), 1)

def test_does_nothing_without_auth_user_table(self):
    self.row().delete()
    with mock.patch.object(connection.introspection, "table_names", return_value=[]):
        self.assertFalse(adopt_auth_user(connection))
    self.assertFalse(self.row().exists())

def test_migrate_prints_adopted_line_only_when_it_acted(self):
    self.row().delete()
    out = StringIO()
    call_command("migrate", plan=True, stdout=out)
    self.assertIn("Adopted the existing auth_user table as accounts.0001_initial.", out.getvalue())
    out = StringIO()
    call_command("migrate", plan=True, stdout=out)
    self.assertNotIn("Adopted", out.getvalue())

def test_migrate_adopts_on_named_database(self):
    self.row().delete()
    with mock.patch("accounts.management.commands.migrate.adopt_auth_user", return_value=False) as adopt:
        call_command("migrate", plan=True, database="default", stdout=StringIO())
    adopt.assert_called_once_with(connections["default"])
```

(`plan=True` only prints the plan, so the test database is never migrated; adoption runs before it, and `TestCase` rolls back the recorder rows.)

- [ ] **Step 4: Run, expect failure.** `python manage.py test accounts.tests.test_adopt` → ImportError on `accounts.adopt`.

- [ ] **Step 5: Implement.**
  - `accounts/adopt.py`: `adopt_auth_user(connection) -> bool` — returns False if `"auth_user" not in connection.introspection.table_names()`; returns False if `MigrationRecorder(connection)` already has `("accounts", "0001_initial")`; otherwise `recorder.ensure_schema()`, `recorder.record_applied("accounts", "0001_initial")`, return True. Docstring says why (spec, "The one-time switch").
  - `accounts/management/commands/migrate.py`: `class Command(django.core.management.commands.migrate.Command)`; `handle(self, *args, **options)` calls `adopt_auth_user(connections[options["database"]])`, writes the exact adopt message to `self.stdout` when True, then `return super().handle(*args, **options)`.

- [ ] **Step 6: Run, expect pass.** `python manage.py test accounts` → OK.

- [ ] **Step 7: Prove adoption on a real existing database.** Work on a copy, never the owner's only `db.sqlite3`: in a worktree copy the main checkout's file in (it is git-ignored); in the main checkout first `cp db.sqlite3 <scratchpad>/db.sqlite3.bak`. Run `python manage.py migrate`. Expected: the adopt line, then no errors and no `InconsistentMigrationHistory`. Run `python manage.py migrate` again: no adopt line. `python manage.py shell -c "from django.contrib.auth import get_user_model as g; print(g().objects.values_list('username', flat=True))"` lists the existing user(s).

- [ ] **Step 8: Full suite.** `python manage.py test` → no failures.

- [ ] **Step 9: Commit.** `git add accounts fortkentcinema/settings.py && git commit -m "feat(accounts): own the user model on auth_user, adopt it on migrate"`

---

### Task 2: Move tests off `username`

The suite must stay green before `username` disappears, so every test creates users through one helper first.

**Files:**
- Create: `accounts/tests/factories.py`
- Modify: `dashboard/tests/helpers.py` (`make_staff`), and every test file that passes `username=` (≈41 files; find them with `grep -rln "username" --include='*.py' */tests`)

**Interfaces:**
- Consumes: `accounts.models.User` (Task 1).
- Produces: `accounts.tests.factories.make_user(email: str = "user@example.com", password: str = "pw12345", **extra) -> User` — at this task it also sets `username=email`; Task 3 deletes that line. `dashboard.tests.helpers.make_staff(email: str = "staffer@example.com", password: str = "pw12345", perms=ALL, **extra) -> User` builds on `make_user`.

- [ ] **Step 1: Add `make_user`** and change `make_staff`'s first parameter from `username` to `email` (default `"staffer@example.com"`), calling `make_user(email, password, is_staff=True, **extra)`.

- [ ] **Step 2: Sweep the call sites.** Each `username="x"` becomes `email="x@example.com"`; every direct `User.objects.create_user(...)` / `create_superuser(...)` in tests becomes `make_user(...)` (superuser: `make_user(..., is_staff=True, is_superuser=True)`). `client.login(username="x", ...)` becomes `client.login(username="x@example.com", ...)` (the backend maps `username` to `USERNAME_FIELD`). POSTs to `/login` send the email in the `username` field. Assertions that expect a username in HTML (e.g. sidebar text) change to expect the email for now; Task 5 changes them again only where it changes the template.

- [ ] **Step 3: Check nothing still names a username.** `grep -rn "username" --include='*.py' */tests | grep -v "\"username\":"` → only POST-dict keys and axes/lockout wording remain.

- [ ] **Step 4: Full suite.** `python manage.py test` → no failures.

- [ ] **Step 5: Commit.** `git commit -am "test: create users by email through one factory"` (add `accounts/tests/factories.py`).

---

### Task 3: Email is the login (model, manager, admin, migration 0002 schema + normalise)

**Files:**
- Create: `accounts/managers.py`, `accounts/migrations/0002_email_login.py`, `accounts/tests/test_models.py`, `accounts/tests/test_migration_0002.py`
- Modify: `accounts/models.py`, `accounts/admin.py`, `accounts/tests/factories.py` (drop `username=email`)

**Interfaces:**
- Consumes: `make_user` (Task 2).
- Produces: `User` with `username = None`, `email = EmailField("email address")`, `USERNAME_FIELD = "email"`, `REQUIRED_FIELDS = []`, `objects = UserManager()`, `get_short_name() -> str` (first name, else email). `UserManager.create_user(email, password=None, **extra)`, `create_superuser(email, password, **extra)`, `get_by_natural_key(email)`. Migration functions `normalise_emails(apps, schema_editor)` in `0002_email_login.py`.

- [ ] **Step 1: Failing model/manager tests** in `accounts/tests/test_models.py`:

```python
def test_save_strips_and_lowercases_email(self):
    self.assertEqual(make_user(email="  Staff@Example.COM ").email, "staff@example.com")

def test_email_unique_ignoring_case_at_the_database(self):
    make_user(email="a@example.com")
    with self.assertRaises(IntegrityError):
        User.objects.bulk_create([User(email="A@example.com")])  # skips save()

def test_create_user_refuses_blank_email(self):
    with self.assertRaises(ValueError):
        User.objects.create_user(email="  ", password="pw")

def test_create_superuser_sets_flags(self):
    u = User.objects.create_superuser(email="Root@Example.com", password="pw")
    self.assertEqual((u.email, u.is_staff, u.is_superuser), ("root@example.com", True, True))

def test_login_ignores_email_case(self):
    make_user(email="staff@example.com", password="pw12345")
    self.assertTrue(self.client.login(username="Staff@Example.com", password="pw12345"))

def test_short_name_falls_back_to_email(self):
    self.assertEqual(make_user(email="a@example.com").get_short_name(), "a@example.com")
    self.assertEqual(make_user(email="b@example.com", first_name="Bea").get_short_name(), "Bea")

def test_has_no_username_field(self):
    self.assertNotIn("username", [f.name for f in User._meta.get_fields()])
```

- [ ] **Step 2: Failing migration tests** in `accounts/tests/test_migration_0002.py` (`TransactionTestCase`). Helper: `migrate_to(target)` with `MigrationExecutor(connection)`; `executor.loader.build_graph()`; `executor.migrate([target])`; returns `executor.loader.project_state([target]).apps`. `setUp` migrates to `("accounts", "0001_initial")`; `tearDown` migrates to `("accounts", "0002_email_login")`. Seed via the old-state `User` model (`username` required):

```python
def test_normalises_existing_emails(self):
    old = migrate_to(("accounts", "0001_initial")).get_model("accounts", "User")
    old.objects.create(username="s", email=" Staff@Example.com ")
    new = migrate_to(("accounts", "0002_email_login")).get_model("accounts", "User")
    self.assertEqual(list(new.objects.values_list("email", flat=True)), ["staff@example.com"])

def test_refuses_duplicate_emails_and_changes_nothing(self):
    old = migrate_to(("accounts", "0001_initial")).get_model("accounts", "User")
    a = old.objects.create(username="a", email="x@example.com")
    b = old.objects.create(username="b", email="X@example.com")
    with self.assertRaisesMessage(RuntimeError, f"[{a.pk}, {b.pk}]"):
        migrate_to(("accounts", "0002_email_login"))
    self.assertEqual(sorted(old.objects.values_list("email", flat=True)), ["X@example.com", "x@example.com"])

def test_refuses_blank_email(self):
    old = migrate_to(("accounts", "0001_initial")).get_model("accounts", "User")
    u = old.objects.create(username="a", email="")
    with self.assertRaisesMessage(RuntimeError, f"[{u.pk}]"):
        migrate_to(("accounts", "0002_email_login"))
```

`tearDown` must delete seeded rows that would block 0002 before migrating forward.

- [ ] **Step 3: Run, expect failure.** `python manage.py test accounts` → failures (username still present, no 0002).

- [ ] **Step 4: Implement the model and manager.** `UserManager(BaseUserManager)`, `use_in_migrations = True`; `normalize_email` here means `strip().lower()` (override the base's domain-only lowercasing); refuses blank with `ValueError("email is required")`; `get_by_natural_key` uses `email__iexact`. `User.save()` and `clean()` normalise the same way (match `Member.save`/`clean` in `audience/models/member.py:217-221`). Add `Meta.constraints = [UniqueConstraint(Lower("email"), name="accounts_user_email_ci_unique")]`.

- [ ] **Step 5: Admin.** `accounts/admin.py`: `@admin.register(User) class UserAdmin(BaseUserAdmin)` with `ordering = ("email",)`, `list_display = ("email", "first_name", "last_name", "is_staff")`, `search_fields = ("email", "first_name", "last_name")`, `fieldsets` = base fieldsets with the first group's fields `("email", "password")`, `add_fieldsets` fields `("email", "password1", "password2")`, and `add_form`/`form` subclasses of `UserCreationForm`/`UserChangeForm` whose `Meta.model = User`, `fields = ("email",)`.

- [ ] **Step 6: Generate and edit 0002.** `python manage.py makemigrations accounts --name email_login`, then arrange the operations in exactly this order (the order makes the migration reversible: reversing re-adds `username` as nullable, fills it, then restores it to unique and required):

  1. `RunPython(normalise_emails, RunPython.noop)`
  2. *(Task 4 inserts `move_user_content_type` here.)*
  3. `AlterField("user", "username", CharField(max_length=150, null=True, blank=True))`
  4. `RunPython(RunPython.noop, fill_username_from_email)`
  5. `RemoveField("user", "username")`
  6. `AlterField("user", "email", ...)`, `AlterModelManagers(...)`, `AddConstraint(...)` as generated.

  `normalise_emails`: compute every user's stripped+lowercased email first; ids with a blank result → `RuntimeError(f"accounts 0002: users with a blank email: {ids}")`; any lowered email held by more than one user → `RuntimeError(f"accounts 0002: users sharing an email: {sorted_ids}")`; only then save. `fill_username_from_email`: `username = email` for every row.

  Add to Step 2's tests: `test_reverse_to_0001_restores_username_from_email` — seed via 0002 state, `migrate_to(("accounts", "0001_initial"))`, assert the 0001-state user's `username == email`.

- [ ] **Step 7: Drop `username=email`** from `make_user`; it now calls `User.objects.create_user(email, password, **extra)`.

- [ ] **Step 8: Run.** `python manage.py test accounts` → OK. Then full `python manage.py test` → no failures.

- [ ] **Step 9: Commit.** `git commit -am "feat(accounts): email is the login, unique ignoring case"` (add new files).

---

### Task 4: Move the user content type in 0002

**Files:**
- Modify: `accounts/migrations/0002_email_login.py` (add `move_user_content_type`), `accounts/tests/test_migration_0002.py`

**Interfaces:**
- Consumes: the migration test helper `migrate_to` (Task 3).
- Produces: `move_user_content_type(apps, schema_editor)` run second in 0002 (after `normalise_emails`, before schema ops); `0002.dependencies` gains `("contenttypes", "0002_remove_content_type_name")` and `("admin", "0003_logentry_add_action_flag_choices")`.

- [ ] **Step 1: Failing tests** (same `TransactionTestCase`). Before migrating to 0002, rename the `accounts | user` content type the test DB already has to `auth | user` (simulating production) via the 0001-state `ContentType` model:

```python
def test_renames_auth_user_content_type(self):
    ...  # make only auth|user exist, with its add/change/delete/view perms
    migrate_to(("accounts", "0002_email_login"))
    self.assertTrue(ContentType.objects.filter(app_label="accounts", model="user").exists())
    self.assertFalse(ContentType.objects.filter(app_label="auth", model="user").exists())

def test_group_permission_survives_content_type_move(self):
    ...  # group holding auth|user change_user; user in that group
    migrate_to(("accounts", "0002_email_login"))
    self.assertTrue(User.objects.get(pk=uid).has_perm("accounts.change_user"))

def test_both_content_types_merge_into_accounts(self):
    ...  # both exist; a group holds the auth one's change_user; a LogEntry points at the auth one
    migrate_to(("accounts", "0002_email_login"))
    # one content type left; group now holds accounts.change_user; LogEntry repointed
```

(No test needed for "neither exists": the fresh test DB already runs that path every run.)

- [ ] **Step 2: Run, expect failure.**

- [ ] **Step 3: Implement `move_user_content_type`.** Get historical `ContentType`, `Permission`, `LogEntry` from `apps`. Old = `auth|user`, new = `accounts|user`. Old only → set `app_label="accounts"`, save. Both → for each old permission: if new has same codename, move its `group_set` and `user_set` links to the new permission then delete the old; else repoint `content_type`; repoint `LogEntry.content_type`; delete old content type. Neither / new only → return. Reverse: `RunPython.noop`.

- [ ] **Step 4: Run.** `python manage.py test accounts` → OK.

- [ ] **Step 5: Commit.** `git commit -am "feat(accounts): carry user permissions across to accounts.user"`

---

### Task 5: Sign-in screens and lockout use email

**Files:**
- Create: `accounts/forms.py`, `accounts/lockout.py`, `accounts/tests/test_lockout.py`
- Modify: `fortkentcinema/urls.py:46` (`authentication_form=EmailAuthenticationForm`), `dashboard/templates/dashboard/login.html:18-24`, `dashboard/templates/dashboard/locked_out.html:20`, `dashboard/templates/dashboard/_sidebar.html:58`, `fortkentcinema/settings.py` (`AXES_USERNAME_CALLABLE = "accounts.lockout.lockout_username"`, and the comments at lines ~233 and ~243 to say email), `dashboard/tests/test_login.py`

**Interfaces:**
- Produces: `accounts.forms.EmailAuthenticationForm(AuthenticationForm)` with `username = UsernameField(label="Email", widget=forms.EmailInput(attrs={"autofocus": True, "autocomplete": "email"}))`; `accounts.lockout.lockout_username(request, credentials: dict | None) -> str`.

- [ ] **Step 1: Failing tests.** In `dashboard/tests/test_login.py`:

```python
def test_login_asks_for_email(self):
    html = self.client.get("/login").content.decode()
    self.assertIn('type="email"', html)
    self.assertIn('autocomplete="email"', html)
    self.assertIn(">Email<", html)

def test_wrong_password_says_email(self):
    resp = self.client.post("/login", {"username": "staffer@example.com", "password": "no"})
    self.assertContains(resp, "Invalid email or password.")

def test_login_ignores_email_case(self):
    resp = self.client.post("/login", {"username": "Staffer@Example.com", "password": "pw12345"})
    self.assertEqual(resp["Location"], "/dashboard/")
```

In `LoginLockoutTests`, add `test_mixed_case_tries_count_against_one_email`: alternate `"staffer@example.com"` / `"STAFFER@example.com"` for `AXES_FAILURE_LIMIT` bad tries → the next correct-password post returns 429. Keep `assertNotIn("staffer@example.com", html)` on the locked-out page. In `accounts/tests/test_lockout.py`: `test_lockout_username_strips_and_lowercases` (`credentials={"username": " A@X.com "}` → `"a@x.com"`; `credentials=None` with POST `username=" B@X.com"` → `"b@x.com"`; missing → `""`). Sidebar test (in the existing chrome/sidebar test file): a user with `first_name="Bea"` sees `Bea`; without a first name sees the email.

- [ ] **Step 2: Run, expect failure.**

- [ ] **Step 3: Implement** the form, `lockout_username` (prefer `credentials["username"]`, else `request.POST.get("username", "")`; `strip().lower()`), the URL kwarg, the setting, and the template copy: label "Email", error "Invalid email or password.", lockout page "email address" in place of "username", sidebar `{{ request.user.get_short_name }}`.

- [ ] **Step 4: Run.** `python manage.py test dashboard accounts` → OK; then full suite → no failures.

- [ ] **Step 5: Commit.** `git commit -am "feat(dashboard): sign in with email; lockout ignores case"` (add new files).

---

### Task 6: Docs and rehearsals

**Files:**
- Modify: `README.md` (lockout section: `axes_reset_username <email>`; new short "Email login" note with the deploy order from the spec), `../ansible/deploy.md` (a line under "Post-deploy steps": back up first; the deploy's migrate adopts `auth_user` and applies `accounts 0002`; staff now sign in with email). The ansible repo is edited but **not** committed.

- [ ] **Step 1: Write the docs** per the spec's "Deploy order".

- [ ] **Step 2: SQLite rehearsal.** In the worktree, replace `db.sqlite3` with a fresh copy of the main checkout's. `python manage.py migrate` → adopt line, `accounts.0002_email_login... OK`. Then `python manage.py shell -c "from django.contrib.auth import get_user_model as g; print(list(g().objects.values_list('email','is_staff')))"` → existing user(s) with lowercase email. `python manage.py runserver` and sign in at `/login` with that email (or `client.login` in the shell if no password is known); confirm the sidebar renders.

- [ ] **Step 3: Postgres rehearsal (docker is available).** `docker run --rm -d --name fkc-pg -e POSTGRES_PASSWORD=pw -e POSTGRES_DB=fkc -p 5432:5432 postgres:16`. Check out `main` in a scratch worktree, point it at the container with `USE_POSTGRES=1 DB_DB=fkc DB_USER=postgres DB_PASSWORD=pw DB_HOST=localhost` (settings leave `PORT` blank, so the container must publish 5432: `-p 5432:5432`; it was free on 2026-10-23; psycopg2-binary is installed), `migrate`, create two staff with groups and one with a mixed-case email. Then from `feat/email-login`, `migrate` against the same DB → adopt line, 0002 OK; the mixed-case email is lowercased; group permissions intact (`has_perm("accounts.change_user")` for the group member). `docker stop fkc-pg`. If 5432 is taken or docker fails, report the rehearsal as not done rather than editing settings.

- [ ] **Step 4: Lint gate.** flake8 on changed lines only (Global Constraints) → no findings.

- [ ] **Step 5: Full suite.** `python manage.py test` → no failures; record the count.

- [ ] **Step 6: Commit.** `git commit -am "docs: email login deploy notes"`, then stop and report to the owner (rehearsal results, suite count, ansible edit uncommitted).
