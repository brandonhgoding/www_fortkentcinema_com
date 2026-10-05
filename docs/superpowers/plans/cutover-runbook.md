# Cutover Runbook: www.fortkentcinema.com / fortkentcinema.com → Django

**Status: documentation only. Nothing in this file has been executed.** It
describes the human-gated steps to cut `www.fortkentcinema.com` and
`fortkentcinema.com` over from the static React build to this Django app
(`api_fortkentcinema_com`), which is already deployed on the same box serving
`api.fortkentcinema.com`.

No DNS change is required: both domains already resolve to the prod EC2 box
(`44.219.163.176`). This is purely an nginx/TLS-cert reconfiguration on that
box, driven by the existing ansible setup at
`/Users/bgoding/code/SoftwareMaine/ansible`.

---

## 1. Pre-flight

- [ ] Merge `feat/django-frontend-migration` into whichever branch the
      deploy pulls (`main`), or point the deploy at the feature branch for a
      one-off cutover. The ansible `django_app` role clones/pulls
      `app.src` (`{{ playbook_dir }}/../api_fortkentcinema_com`) at deploy
      time, so the ansible box's checkout must have this work.
- [ ] `python manage.py test` green (87 tests as of this task; includes the
      new `ProdSecuritySettingsTests`).
- [ ] `python manage.py collectstatic --noinput` runs clean locally with
      `DEBUG=False` set, to catch any missing/broken static references before
      the real deploy does it.
- [ ] Confirm `python manage.py check --deploy` has no unaddressed
      warnings once the prod env vars below are exported locally (sanity
      check only — the real settings are only ever set in the vaulted
      ansible `env_vars`, never locally).
- [ ] Confirm this repo's `requirements.txt` now includes `gunicorn==23.0.0`
      (added by this task) — belt-and-suspenders, since the `django_app` role
      also installs `gunicorn` into the shared venv independently of the
      app's own `requirements.txt`.

## 2. Production environment variables

These are set as vaulted `env_vars` under `django_apps` in
`ansible/group_vars/webservers.yml` (see the change in Section 3) — **not**
committed in plaintext, and not applied by this task. As of the Section 3
revision below, these apply to **two** `django_apps` entries
(`api_fortkentcinema_com` and the new `www_fortkentcinema_com`), not just
one — see the note at the end of this section.

| Var | Value |
|---|---|
| `DEBUG` | `False` |
| `ALLOWED_HOSTS` | `www.fortkentcinema.com,fortkentcinema.com,api.fortkentcinema.com` |
| `USE_PROXY_HEADERS` | `True` |
| `SECURE_SSL_REDIRECT` | `True` |
| `SESSION_COOKIE_SECURE` | `True` |
| `CSRF_COOKIE_SECURE` | `True` |
| `CSRF_TRUSTED_ORIGINS` | `https://www.fortkentcinema.com,https://fortkentcinema.com,https://api.fortkentcinema.com` |
| `SECURE_HSTS_SECONDS` | `31536000` |
| `SECURE_HSTS_INCLUDE_SUBDOMAINS` | leave `False` unless every subdomain is confirmed HTTPS-only (`api.` already is, but don't turn this on blind) |
| `SECURE_HSTS_PRELOAD` | leave `False` until HSTS has been live without incident for a while — preload is effectively irreversible |

Values that already exist for this app and must be carried over unchanged
(currently set in `webservers.yml` lines 244–347): `SECRET_KEY`,
`USE_POSTGRES=True` + `DB_DB`/`DB_USER`/`DB_PASSWORD`/`DB_HOST`,
`OMDB_API_KEY`, `GA_MEASUREMENT_ID`, `USE_GMAIL`, `CONTACT_FORM_TO_ADDRESS`,
`EMAIL_HOST_USER`/`EMAIL_HOST_PASSWORD`, `RECAPTCHA_PUBLIC_KEY`/
`RECAPTCHA_PRIVATE_KEY`, `SQUARE_ACCESS_TOKEN`, `SQUARE_ENVIRONMENT`,
`SENTRY_DSN`. `ENABLE_CDN` stays at its current default (off) unless a CDN
migration is planned separately. `LEPRINCEOS_BASE_URL` keeps its code
default (`https://www.leprinceos.com/api/v1`) — no override needed.

`ALLOWED_HOSTS` is the one existing value that **must change** (currently
`api.fortkentcinema.com` only) to add the two new host names.

**Important (revised in this task's review pass):** as explained in Section
3, the cutover adds a **second, separate `django_apps` entry**
(`www_fortkentcinema_com`) rather than extending `api_fortkentcinema_com`'s
`server_names`. That second entry is a fully independent gunicorn process
running the same codebase against the same Postgres database, so it needs
**its own copy of this entire env var table**, including a byte-for-byte
copy of the vaulted `SECRET_KEY` and all `DB_*` values (same DB — different
`SECRET_KEY`s would still work in isolation, but keeping them identical
avoids any surprise if session/CSRF-signed values ever cross hosts). Give
both entries the same broad `ALLOWED_HOSTS` / `CSRF_TRUSTED_ORIGINS`
(`www.fortkentcinema.com,fortkentcinema.com,api.fortkentcinema.com`) — this
list is a Django-level Host-header allowlist, not an nginx routing
directive, so listing all three on both entries is harmless and simpler
than trying to keep two narrower lists in sync.

## 3. Ansible change (propose as a diff; a human applies it — NOT run here)

File: `ansible/group_vars/webservers.yml`.

### ⚠️ Correction from code review: do NOT add www/apex to the existing `api_fortkentcinema_com` entry

An earlier draft of this section proposed adding `www.fortkentcinema.com` +
`fortkentcinema.com` to the **existing** `api_fortkentcinema_com`
`django_apps` entry's `server_names`, with `api.fortkentcinema.com` kept
first. Reading `roles/nginx/templates/django-site.conf.j2` shows that's
wrong — the port-80 server block it renders is:

```
server {
    ...
    location / {
        return 301 https://{{ app.server_names[0] }}$request_uri;
    }

    listen 80;
    server_name {{ app.server_names | join(' ') }};
}
```

This block matches **every** host in `server_names` and redirects **all**
of them to the **same single** `https://{{ server_names[0] }}` target —
there's no per-host branching for plain HTTP. One `django_apps` entry can
only have one canonical "redirect target for all its hosts," not three
independent ones. Concretely, whichever host is listed first "wins" for
every other host in that entry:

- Keep `api.fortkentcinema.com` first (as originally drafted) → plain
  `http://www.fortkentcinema.com` and `http://fortkentcinema.com` 301 to
  `https://api.fortkentcinema.com` — the wrong host for the primary public
  domain.
- Reorder to put `www.fortkentcinema.com` first instead → now plain
  `http://api.fortkentcinema.com` 301s to `https://www.fortkentcinema.com`,
  the wrong host for the API domain. Reordering also changes what
  `roles/certbot/tasks/main.yml` and the `ssl_certificate` line in the same
  template treat as the cert lineage name (`{{ server_names[0] }}`), which
  would silently switch which on-disk cert directory this nginx site
  references (from the existing `api.fortkentcinema.com` lineage to the
  `www.fortkentcinema.com` lineage that already exists from the static
  site being retired) — workable, but it's a second landmine on top of the
  first, and still doesn't fix the underlying problem.

So **no single `server_names` list can make all three hosts redirect
correctly** — a merged entry is structurally incompatible with the "each
host's plain HTTP goes to its own https" requirement. The fix is to keep
`www`/`apex` on their own `django_apps` entry, separate from
`api_fortkentcinema_com`, each with its own `server_names[0]`. This also
matches the only existing precedent in this file for a Django app fronting
its own marketing domain + apex redirect — `cinema_sass`
(`server_names: [www.leprinceos.com, leprinceos.com]`, apex redirected via
the same `nginx_extra_locations: if ($host = ...) {...}` idiom used below).
There is no existing example anywhere in `webservers.yml` of one
`django_apps` entry serving two unrelated public hostnames the way the
earlier draft proposed.

**a. Remove the static site entry** (currently lines ~12–33): delete the
`www_fortkentcinema_com` block from `static_sites`, including its
`VITE_FKC_MEMBERSHIPS_SITE_KEY` vaulted var (no longer needed once the React
build is retired from serving traffic).

**b. Add a NEW `django_apps` entry, `www_fortkentcinema_com`, pointed at the
same Django source as `api_fortkentcinema_com`; leave the existing
`api_fortkentcinema_com` entry's `name`/`service_name`/`server_names`
untouched:**

```yaml
  - name: www_fortkentcinema_com
    service_name: fortkentcinema_www          # NEW — must differ from the
                                               # existing "fortkentcinema"
                                               # service_name: each entry
                                               # gets its own systemd unit
                                               # + gunicorn socket; reusing
                                               # the same service_name would
                                               # make two entries race to
                                               # own the same unit file and
                                               # socket.
    src: "{{ playbook_dir }}/../api_fortkentcinema_com"   # same codebase
    dest: "{{ deploy_base }}/fortkentcinema_www"          # NOT the same
                                                           # path as the old
                                                           # static site's
                                                           # dest (deliberately
                                                           # distinct — see
                                                           # note below and
                                                           # Section 6)
    wsgi_module: fortkentcinema.wsgi:application
    workers: 2                                # lighter than the api
                                               # entry's 3; tune post-launch
    requirements: requirements.txt
    server_names:
      - www.fortkentcinema.com
      - fortkentcinema.com
    media_root: "{{ deploy_base }}/api_fortkentcinema_com/shared/media/"
    # ^ point at the SAME media dir as api_fortkentcinema_com (not a new
    #   .../www_fortkentcinema_com/shared/media/ path) so an upload/image
    #   is visible from both hostnames instead of only whichever process
    #   received it — both entries run the same DB, so media should be a
    #   single shared store too.
    nginx_extra_locations: |
        if ($host = fortkentcinema.com) {
            return 301 https://www.fortkentcinema.com$request_uri;
        }
    env_vars:
      # Copy every existing api_fortkentcinema_com env var byte-for-byte
      # (SECRET_KEY, USE_POSTGRES + DB_DB/DB_USER/DB_PASSWORD/DB_HOST,
      # OMDB_API_KEY, GA_MEASUREMENT_ID, USE_GMAIL, CONTACT_FORM_TO_ADDRESS,
      # EMAIL_HOST_USER/PASSWORD, RECAPTCHA_*, SQUARE_*, SENTRY_DSN — see
      # Section 2), PLUS:
      DEBUG: "False"
      ALLOWED_HOSTS: www.fortkentcinema.com,fortkentcinema.com,api.fortkentcinema.com
      USE_PROXY_HEADERS: "True"
      SECURE_SSL_REDIRECT: "True"
      SESSION_COOKIE_SECURE: "True"
      CSRF_COOKIE_SECURE: "True"
      CSRF_TRUSTED_ORIGINS: "https://www.fortkentcinema.com,https://fortkentcinema.com,https://api.fortkentcinema.com"
      SECURE_HSTS_SECONDS: "31536000"
    # Deliberately OMITTED: cron_pg_dump, cron_clearsessions,
    # cron_flushexpiredtokens, cron_membership_cleanup,
    # cron_membership_email_retry. Those stay set only on the
    # api_fortkentcinema_com entry — both entries share the same DB, so
    # enabling them here too would run every cron job (including the daily
    # pg_dump backup and the membership-cleanup/session-clearing jobs)
    # twice against the same tables.
```

**Also update the existing `api_fortkentcinema_com` entry** (leave `name`,
`service_name`, `server_names` = `[api.fortkentcinema.com]` alone), but add
the same new security env vars from Section 2 (`USE_PROXY_HEADERS`,
`SECURE_SSL_REDIRECT`, `SESSION_COOKIE_SECURE`, `CSRF_COOKIE_SECURE`,
`SECURE_HSTS_SECONDS`) and broaden `ALLOWED_HOSTS` /
`CSRF_TRUSTED_ORIGINS` to the same three-host list used above, for
consistency between the two processes running the same code. This does
**not** change its `server_names`/nginx routing/cert at all.

Notes on why this is the right shape, from reading the ansible roles:

- `django-site.conf.j2` (`roles/nginx/templates/django-site.conf.j2`)
  renders one `server_name {{ app.server_names | join(' ') }}` for both its
  443 and port-80 blocks **per `django_apps` entry**, with the port-80
  block always redirecting to `https://{{ app.server_names[0] }}`
  regardless of which host in the list was hit (quoted above). Keeping
  `www_fortkentcinema_com` as its own entry with `server_names[0] =
  www.fortkentcinema.com` means its port-80 block only ever redirects
  www/apex traffic to `https://www...`; `api_fortkentcinema_com`'s own
  port-80 block (unchanged, `server_names: [api.fortkentcinema.com]`)
  still only redirects to `https://api...`. Each host redirects to itself.
- The apex→www redirect uses the exact same `nginx_extra_locations: if
  ($host = ...) { return 301 ...}` idiom already used by the
  `www_fortkentcinema_com` static entry (and by `cinema_sass`/
  `www_leprinceos_com`) — copied here so `fortkentcinema.com` still 301s to
  `www.fortkentcinema.com`, now served by Django instead of nginx `alias`ed
  static files.
- `roles/certbot/tasks/main.yml` obtains the cert if missing, or **expands**
  it (`certbot certonly ... --expand -d <server_names joined>`) if
  `/etc/letsencrypt/live/{{ server_names[0] }}/fullchain.pem` already
  exists. For the new `www_fortkentcinema_com` entry, `server_names[0]` is
  `www.fortkentcinema.com`, and that cert lineage **already exists** (it's
  the retiring static site's cert, covering the same www + apex names) —
  so this is a same-name expand with the identical SAN set, which certbot
  reports as "no action taken." `api_fortkentcinema_com`'s own
  `api.fortkentcinema.com` cert lineage is completely untouched. No manual
  certbot invocation needed; the ansible run handles it.
- **New-entry gotcha:** `roles/common/tasks/main.yml` ("Create log
  directories for all django apps") is what creates
  `/var/log/{{ service_name }}/` for every `django_apps` entry, and it's
  tagged `common`, not `deploy`. Because `common` isn't in the
  `--tags deploy,nginx,certbot` set this runbook's Section 4 uses,
  `/var/log/fortkentcinema_www/` won't exist yet for a **brand-new** entry
  unless `common` is included in that first run — gunicorn's
  `--access-logfile`/`--error-logfile` flags would then fail to open, and
  the new systemd service would fail to start. Section 4 below adds
  `common` to the first deploy of the new entry to cover this.
- `site.yml`'s `pre_tasks` filter `django_apps`/`static_sites` down to a
  single entry when `-e deploy_app=<name>` is passed, and **clear the other
  list entirely** when it doesn't match. That means a
  `-e deploy_app=www_fortkentcinema_com` run (after Section 3a's deletion
  from `static_sites` and Section 3b's addition to `django_apps` are both
  applied in the same commit) resolves `www_fortkentcinema_com` as a
  `django_apps` name, not a `static_sites` name, so it deploys the new
  Django entry and touches nothing else. No separate destroy step is
  required for the old static site; if you want the old static file tree
  cleaned off disk that's a manual `rm -rf` on the box (optional cosmetic
  cleanup, not required for cutover correctness).

## 4. Deploy (human-run; NOT executed by this task)

Two separate `django_apps` entries now need deploying — run them as two
separate invocations so a mistake in one doesn't also touch the other.

From the ansible repo, against the `webservers` inventory group:

```bash
# 1. Existing api entry — picks up the new security env vars only;
#    server_names/nginx/cert are unchanged for this entry.
ansible-playbook site.yml --tags deploy,nginx,certbot -e deploy_app=api_fortkentcinema_com

# 2. NEW www/apex entry — first-time deploy, so include `common` as well
#    (creates /var/log/fortkentcinema_www/ before gunicorn starts — see the
#    "New-entry gotcha" note in Section 3).
ansible-playbook site.yml --tags common,deploy,nginx,certbot -e deploy_app=www_fortkentcinema_com
```

Run #1 (per `site.yml`'s task list, filtered to the one app by the
pre_tasks above) will:

1. Run the `django_app` role (`tags: deploy`): pull the merged branch,
   install/upgrade the shared venv (`requirements.txt`, now including
   `gunicorn==23.0.0`), run `manage.py migrate --noinput`, run
   `manage.py collectstatic --noinput`, and restart the `fortkentcinema`
   systemd/gunicorn service to pick up the new env vars. `server_names`
   for this entry does not change.
2. Run the `certbot` role (`tags: certbot`): no new SANs for
   `api.fortkentcinema.com`'s cert, so this is a no-op expand.
3. Run the `nginx` role (`tags: nginx`): re-render
   `/etc/nginx/sites-available/api_fortkentcinema_com` (still just
   `api.fortkentcinema.com`), validate with `nginx -t`, and reload nginx.

Run #2 will:

1. Run the `common` role (`tags: common`): create
   `/var/log/fortkentcinema_www/` (and anything else common creates for
   every `django_apps` entry) before the new service tries to start.
2. Run the `django_app` role (`tags: deploy`): rsync the code into a
   **new** `{{ deploy_base }}/fortkentcinema_www` release tree (deliberately
   a different path from the old static site's
   `{{ deploy_base }}/www_fortkentcinema_com` — keeps the retiring static
   build completely untouched on disk for a clean rollback), build a
   **new, separate** shared venv there, run `manage.py migrate --noinput`
   (idempotent — same DB/migration state as the api entry) and
   `manage.py collectstatic --noinput` into its own `staticfiles/`, deploy
   and start a **new** `fortkentcinema_www` systemd/gunicorn service (its
   own socket, own memory allocation, independent of `fortkentcinema`).
3. Run the `certbot` role (`tags: certbot`): expand the existing
   `www.fortkentcinema.com` cert lineage (retained from the static site) —
   already covers `www.fortkentcinema.com` + `fortkentcinema.com`, so this
   is also a no-op expand.
4. Run the `nginx` role (`tags: nginx`): re-render
   `/etc/nginx/sites-available/www_fortkentcinema_com` — same filename the
   static site used, now templated from `django-site.conf.j2` instead of
   `static-site.conf.j2` — with `server_name www.fortkentcinema.com
   fortkentcinema.com`, the apex redirect block, `proxy_pass` to the new
   `fortkentcinema_www` gunicorn socket, validate with `nginx -t`, reload.

Because `deploy_app` filters `static_sites` to empty when it doesn't match
`static_sites` names, and `www_fortkentcinema_com` is no longer a
`static_sites` name once Section 3a's removal is applied, run #2 resolves
against `django_apps` only and does not re-invoke the (deleted) static-site
role for that name. The entry removal in Section 3a is what makes the
change durable for future full (`deploy_app`-less) runs.

## 5. Verification (human-run)

- [ ] `curl -I https://www.fortkentcinema.com/` returns `200` with a
      Django-rendered page (check for the `Server` header switching away
      from whatever nginx reports for static file serving, and confirm the
      HTML is the Django template output, not the old Vite `index.html`).
- [ ] `curl -s https://www.fortkentcinema.com/blog/<any-existing-slug> |
      grep -i 'og:'` shows per-post Open Graph tags (title, absolute
      `og:image`, `og:url`) — the SEO polish from Task 2.
- [ ] `curl -s https://www.fortkentcinema.com/sitemap.xml` and
      `.../robots.txt` both resolve (Task 1).
- [ ] `curl -I https://fortkentcinema.com/` returns a `301` to
      `https://www.fortkentcinema.com/`.
- [ ] **Plain-HTTP redirect targets — each host must redirect to ITSELF,
      not cross-redirect to a different host** (this is the behavior the
      code review flagged and Section 3 fixes):
      ```bash
      curl -sI http://www.fortkentcinema.com/   # expect: 301 Location: https://www.fortkentcinema.com/...
      curl -sI http://fortkentcinema.com/       # expect: 301 Location: https://www.fortkentcinema.com/...
      curl -sI http://api.fortkentcinema.com/   # expect: 301 Location: https://api.fortkentcinema.com/...
      ```
      Fail this check (and stop / roll back) if `api.fortkentcinema.com`'s
      plain-HTTP request redirects anywhere other than
      `https://api.fortkentcinema.com` — that would mean the two
      `django_apps` entries got merged back into one (or `server_names[0]`
      on the `api_fortkentcinema_com` entry changed) and the original bug
      is back.
- [ ] `curl -s https://api.fortkentcinema.com/api/posts/` still returns
      data — confirm the API host is unaffected by this cutover (its
      `django_apps` entry's `server_names`/nginx config did not change).
- [ ] `systemctl is-active fortkentcinema fortkentcinema_www` both report
      `active` — confirms both gunicorn processes (api entry and the new
      www/apex entry) are up as independent services.
- [ ] Spot-check the browser: homepage, now-showing, a blog post, `/about`,
      `/rentals` all render with images/CSS/JS loading from `/static/` (no
      404s in devtools network tab) — confirms whitenoise `collectstatic`
      picked up correctly and the `/static/` nginx `alias` in
      `django-site.conf.j2` points at the right `static_root`.
- [ ] Check `Strict-Transport-Security` response header is present once
      `SECURE_HSTS_SECONDS=31536000` is live, and only proceed to also
      setting `SECURE_HSTS_INCLUDE_SUBDOMAINS`/`SECURE_HSTS_PRELOAD` after
      confirming no subdomain is HTTP-only.

## 6. Rollback

If verification fails, revert to serving the static React build:

1. In `ansible/group_vars/webservers.yml`:
   - Re-add the `www_fortkentcinema_com` entry to `static_sites` (restore
     from git history / this runbook's Section 3a).
   - Remove the entire new `www_fortkentcinema_com` entry from
     `django_apps` (Section 3b) — do **not** try to edit it in place; just
     delete the block.
   - Optionally revert the security env vars added to the
     `api_fortkentcinema_com` entry (`USE_PROXY_HEADERS`,
     `SECURE_SSL_REDIRECT`, `SESSION_COOKIE_SECURE`, `CSRF_COOKIE_SECURE`,
     `SECURE_HSTS_SECONDS`, broadened `ALLOWED_HOSTS`/
     `CSRF_TRUSTED_ORIGINS`) — not required for rollback correctness since
     that entry's `server_names`/nginx routing never changed, but tidy to
     restore if the rollback is expected to be long-lived rather than a
     quick fix-and-retry.
2. Re-run, once per app name so each resolves against the right role:
   ```bash
   ansible-playbook site.yml --tags deploy,nginx,certbot -e deploy_app=www_fortkentcinema_com
   ansible-playbook site.yml --tags deploy,nginx,certbot -e deploy_app=api_fortkentcinema_com
   ```
   The first run now resolves `www_fortkentcinema_com` back against
   `static_sites` (since it was removed from `django_apps` in step 1) and
   re-renders `/etc/nginx/sites-available/www_fortkentcinema_com` from
   `static-site.conf.j2` again, pointed at the untouched
   `{{ deploy_base }}/www_fortkentcinema_com/dist` build. The second run is
   a no-op for `api_fortkentcinema_com` beyond reverting whatever env vars
   changed in step 1.
3. The React build under `{{ deploy_base }}/www_fortkentcinema_com` was
   never touched by the cutover — the new Django deployment used a
   deliberately different path, `{{ deploy_base }}/fortkentcinema_www`
   (see Section 3b) — so the `static_site` role's re-run just re-links the
   existing build with no rebuild needed for an immediate rollback.
4. Stop and disable the now-orphaned `fortkentcinema_www` systemd service
   on the box (the `django_app` role has no "destroy" step, same as the
   static-site removal case in Section 3): `sudo systemctl stop
   fortkentcinema_www && sudo systemctl disable fortkentcinema_www`. The
   release tree at `{{ deploy_base }}/fortkentcinema_www` can be left in
   place or `rm -rf`'d — optional cosmetic cleanup, not required for the
   rollback to take effect.
5. Verify `https://www.fortkentcinema.com/` serves the React `index.html`
   again, `https://fortkentcinema.com` still 301s to `www`, and
   `https://api.fortkentcinema.com/api/posts/` is unaffected throughout.

## 7. Square sync

Ship with the token blank, so deploying the code changes nothing visible.
With `SQUARE_ACCESS_TOKEN` empty, `pull_square_sales` and `sync_square_catalog`
print `Square sync disabled (no SQUARE_ACCESS_TOKEN)` and exit 0.

### Environment variables (`webservers.yml`)

- `SQUARE_ACCESS_TOKEN` (leave blank until cutover)
- `SQUARE_LOCATION_ID`
- `SQUARE_TICKET_CATEGORY_ID` (the Movies category)
- `SQUARE_ENVIRONMENT=production` (defaults to `sandbox`)
- `EMAIL_HOST`
- `EMAIL_PORT` (default 587)
- `EMAIL_HOST_USER`
- `EMAIL_HOST_PASSWORD`
- `EMAIL_USE_TLS` (default True)
- `DEFAULT_FROM_EMAIL`

Deploy note: `requirements.txt` bumped `typing_extensions` from 4.14.0 to
4.16.0 (required by the Square SDK's `anyio` dependency); the deploy's
`pip install -r requirements.txt` picks it up.

### Cron lines (Ansible repo, `webservers.yml`)

Adjust the path to the deployed checkout. The times are Eastern wall-clock
(the pull at 23:45 must see the whole evening's sales); `CRON_TZ` makes cron
read them that way even if the server's clock is UTC.

```
CRON_TZ=America/New_York
45 23 * * *  cd /srv/www_fortkentcinema_com && .venv/bin/python manage.py pull_square_sales
0  2  * * *  cd /srv/www_fortkentcinema_com && .venv/bin/python manage.py sync_square_catalog
```

Command flags: `pull_square_sales [--date YYYY-MM-DD] [--days N] [--dry-run]
[--no-email]` and `sync_square_catalog [--dry-run]`.

### Admin steps

In Django admin, Box Office, Email reports: enter the To and CC recipients
for both reports, and set the ticket report's subject (seeded as "Ticket
Sales Report"; the owner may change it). `EmailRecipient` rows marked CC do
not count as a To address, and a report with no To address is skipped.

### Rollout (from the spec)

1. **Square side.** Create a Developer application with catalog read/write
   and orders read scopes. Record the production location ID and the Movies
   category ID. Confirm the sandbox equivalents for local use.
2. **Server side.** Add `SQUARE_*` and `EMAIL_*` to `webservers.yml`; deploy;
   `migrate`. In the admin, enter the recipients for both reports. Run
   `sync_square_catalog --dry-run` and read what it would push.
   - **Sandbox smoke test, before production.** With sandbox credentials
     (`SQUARE_ENVIRONMENT=sandbox` and the sandbox token, location and
     category IDs), create one run in the dashboard and confirm it; watch its
     item appear in the sandbox Square dashboard. Rename it and watch the item
     rename. Cancel it and watch the item disappear. Then run both commands
     for real once (`sync_square_catalog` and `pull_square_sales`, without
     `--dry-run`) and check their output. Only then switch to production
     credentials.
   - **Warning: until the Square-side deletion in step 3, only use
     `--dry-run`.** On production credentials, a non-dry `sync_square_catalog`
     or any dashboard save of a *current* confirmed run creates a Django item
     beside the still-present hand-made one, and the register shows both. On
     cutover evening, do the Square-side deletion first, and do not edit
     current runs in the dashboard before it.
3. **Cutover, on a run boundary.** After the last show of the current runs
   has started: delete every hand-made ticket item in Square (not the Movies
   category). There is nothing to mark in Django: those runs end at their
   `end_date`, and the 02:00 reconcile retires any Django items for them the
   next night. Then confirm the new week's runs in the dashboard and watch the
   items appear. Staff pin the new items to the
   register's favorites grid and stop using the matinee discount. The empty
   Events and Pre-Sales categories can be removed in Square or left; Django
   never uses them.
4. **Reports.** Run `pull_square_sales --dry-run` for the cutover day and
   compare against the old script's output for the same day. The old script
   lives outside this repository, so this comparison is manual: run it as
   usual and set the two outputs side by side. Then add the two
   cron entries and retire the script's cron.
5. **Verify over the first week** that `admissions` is filling and the
   ticket report matches what the booker received before.
