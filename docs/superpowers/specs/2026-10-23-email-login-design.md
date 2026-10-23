# Email login

**Date:** 2026-10-23
**Status:** Approved design, awaiting spec review

## Intent

The owner wants a members' area, separate from the dashboard, where members
sign in, vote on films and buy tickets at the member rate. The first step is
the identity underneath it: **a user's email is their login, and there is no
separate username.** This applies to every account, staff included, so the
dashboard login switches to email as well.

Decisions made with the owner:

- **Custom user model** (option A of three): a project-owned `accounts.User`
  with no `username` field, rather than keeping Django's built-in `User` and
  logging in by email, or storing the email in `username`.
- **Staff sign in with email too.** Members and staff share one user model;
  a member account is simply `is_staff=False`.
- **Staff emails are already unique** in production (owner, 2026-10-23).

Out of scope here, each to be designed separately and in this order:

1. Member accounts: registration, linking an account to an `audience.Member`
   record, password reset, the members' area pages.
2. Member voting.
3. The member ticket rate in online checkout.

## The model

A new app, `accounts`, added to `INSTALLED_APPS`, with:

```python
class User(AbstractUser):
    username = None
    email = models.EmailField("email address")  # uniqueness: see constraint

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS = []

    objects = UserManager()

    class Meta:
        db_table = "auth_user"
        constraints = [
            UniqueConstraint(Lower("email"), name="accounts_user_email_ci_unique"),
        ]
```

- **Normalised email.** `save()` and `clean()` strip and lowercase the email,
  the same way `Member` and `Subscriber` already do. The functional unique
  constraint backs that up at the database, so two spellings of one address
  can never both exist even if a write skips `save()`.
- **Same table.** `db_table = "auth_user"` keeps every existing row, password
  hash and `last_login`. Django names auto-created many-to-many tables after
  the model's table, so `groups` and `user_permissions` resolve to the
  existing `auth_user_groups` and `auth_user_user_permissions` (columns
  `user_id`, `group_id`, `permission_id`), and every group and permission
  assignment carries over untouched.
- **`UserManager`** (in `accounts/managers.py`, subclassing `BaseUserManager`):
  `create_user(email, password=None, **extra)` and
  `create_superuser(email, password, **extra)`, both normalising the email
  and refusing a blank one. `get_by_natural_key(email)` looks up with
  `email__iexact`, so logging in as `Brandon@…` finds `brandon@…`.
- **Setting:** `AUTH_USER_MODEL = "accounts.User"`. The two existing foreign
  keys (`tickets.TicketOrder.redeemed_by`, `audience.FreeAdmission.recorded_by`)
  already point at `settings.AUTH_USER_MODEL` and need no model change.
- `get_short_name()` returns `first_name`, falling back to the email.

## Migrations

**`accounts 0001_initial`** creates `User` exactly as Django's built-in
`auth.User` stands today: same fields (`username` included), same table
name, same many-to-many tables. On a fresh database (every test run, any new
developer machine) it builds `auth_user` from scratch; Django's own `auth`
migrations skip the swapped-out model.

**`accounts 0002_email_login`**, in order:

1. **Data check and normalise.** Lowercase and strip every email. If any user
   has a blank email, or two users share an email once lowercased, stop with
   an error naming the affected user ids. Nothing is changed in that case
   (the migration runs in a transaction on Postgres).
2. **Move the content type.** Rename the `auth | user` content type to
   `accounts | user` so that the `add_user`/`change_user`/… permissions,
   any group holding them, and admin log entries keep pointing at the user
   model. If both content types already exist, repoint permissions and log
   entries from the old to the new and delete the old. If neither exists
   (a fresh database), do nothing; `post_migrate` creates it.
3. **Schema.** Remove `username`, and add the case-insensitive unique
   constraint on email.

Reverse migration: step 3 reverses by re-adding `username` and filling each
row with that user's email; steps 1 and 2 are no-ops in reverse. A rollback is
not expected, but `migrate accounts 0001` must not crash.

### The one-time switch on existing databases

Django does not support changing `AUTH_USER_MODEL` on a database that
already has tables. On the production database (Postgres) and any existing
local database (`db.sqlite3`), `auth_user` already exists, and
`audience 0008` and `tickets 0001` are recorded as applied while depending on
the user model's first migration. Running `migrate` straight away fails with
`InconsistentMigrationHistory`.

The fix is to record `accounts 0001` as applied before migrating, because
its table already exists. The ansible role runs `manage.py migrate --noinput`
on every deploy (and `rollback.yml` does too), so there is no point at which
a separate command could run first. **The accounts app therefore ships its
own `migrate` command** (owner's choice, 2026-10-23, over an ansible
pre-migrate hook or a deliberately failing two-pass deploy):

- `accounts/management/commands/migrate.py` subclasses Django's `migrate`
  command. Before calling the parent's `handle()`, it calls
  `adopt_auth_user(connection)` for the database named by `--database`.
- `adopt_auth_user` (in `accounts/adopt.py`) records `accounts.0001_initial`
  in `django_migrations` when, and only when, the `auth_user` table exists and
  that row is missing. It returns whether it acted; the command prints
  "Adopted the existing auth_user table as accounts.0001_initial." when it
  did, and nothing otherwise.
- On a fresh database (no `auth_user`, as when the test runner builds its
  database) and on every deploy after the first, it does nothing.
- It writes nothing else. `migrate` then applies `0002` as normal.

It must run before the parent's consistency check, so it uses the connection
and `MigrationRecorder` directly and never builds the migration graph.

**Deploy order** (noted in `README.md` and `../ansible/deploy.md`):

1. Back up the database.
2. Deploy as usual. The deploy's own `migrate` adopts the table and applies
   `0002`.
3. Sign in to the dashboard with your email address.

Before handing this over, the switch is rehearsed on a copy of the local
`db.sqlite3`, and on a Postgres database restored from a production-shaped
dump if one is available. Any rehearsal not done is reported as not done.

## What changes on screen

- **Dashboard login** (`dashboard/templates/dashboard/login.html`): the label
  reads "Email", the input is `type="email"` with `autocomplete="email"`,
  and the error reads "Invalid email or password." `AuthenticationForm`
  already labels and validates its first field from `USERNAME_FIELD`; the
  POST field stays named `username`.
- **Lockout page** (`locked_out.html`): wording changes from username to
  email address.
- **Sidebar** (`_sidebar.html`): shows `get_short_name` (first name, else
  email) instead of `request.user.username`. `dashboard/views.py`'s
  `display_name` keeps its existing `get_short_name() or get_username()`
  logic, which now yields the email.
- **Ticket order row** "Arrived · …": unchanged template; its
  `get_username` fallback now yields the email.
- **Django admin:** a `UserAdmin` subclass registered for `accounts.User`,
  with `username` removed from fieldsets, add form, list display, search and
  ordering, and email in their place. `createsuperuser` prompts for email.

## Login lockout (django-axes)

`AXES_LOCKOUT_PARAMETERS` stays `[["username", "ip_address"]]`. axes reads
the POST field named `username`, which still carries the login. Add
`AXES_USERNAME_CALLABLE` pointing at a small function that returns the
submitted value stripped and lowercased, so `A@x.com` and `a@x.com` count
against the same five tries.

## Testing

Test-first throughout. New tests in `accounts/tests/`:

- Saving a user lowercases and strips the email; a second user with the same
  email in different case is refused by the database constraint.
- `create_user` / `create_superuser` normalise the email and refuse a blank one.
- Login through the dashboard login page succeeds with differently-cased
  email; fails with the wrong password with the new error wording.
- Migration 0002 (driven with Django's `MigrationExecutor`, migrating to
  0001, seeding rows, then migrating to 0002): normalises emails; refuses on a duplicate
  and on a blank email, changing nothing; moves the `auth.user` content type
  and its permissions; is a no-op on a fresh database.
- `adopt_auth_user` and the `migrate` override: records 0001 when
  `auth_user` exists and the row is missing; a second call changes nothing;
  does nothing when `auth_user` is absent; `migrate` prints the adopted line
  only when it acted.
- Lockout: five bad tries with mixed-case versions of one email lock that
  email out (`override_settings(AXES_ENABLED=True, ...)`, as the existing
  lockout tests do).

Existing tests: about 42 test files create users with `username=`. They move
to `email=` (or a shared helper in `accounts/tests/factories.py` if that
reads cleaner where many users are made). No test is deleted or weakened to
make the suite pass.

Done means: the full suite is green, no new flake8 findings on changed lines
(per the repo's lint baseline rule), and the adopt-then-migrate rehearsal has
succeeded on a copy of the local database.
