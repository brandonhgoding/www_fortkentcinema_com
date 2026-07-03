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

These are set as vaulted `env_vars` on the `api_fortkentcinema_com` entry
under `django_apps` in `ansible/group_vars/webservers.yml` (see the change in
Section 3) — **not** committed in plaintext, and not applied by this task.

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

## 3. Ansible change (propose as a diff; a human applies it — NOT run here)

File: `ansible/group_vars/webservers.yml`.

**a. Remove the static site entry** (currently lines ~12–33): delete the
`www_fortkentcinema_com` block from `static_sites`, including its
`VITE_FKC_MEMBERSHIPS_SITE_KEY` vaulted var (no longer needed once the React
build is retired from serving traffic).

**b. Extend the `api_fortkentcinema_com` `django_apps` entry** (currently
lines ~232–347):

```yaml
  - name: api_fortkentcinema_com
    service_name: fortkentcinema
    src: "{{ playbook_dir }}/../api_fortkentcinema_com"
    dest: "{{ deploy_base }}/api_fortkentcinema_com"
    wsgi_module: fortkentcinema.wsgi:application
    workers: 3
    requirements: requirements.txt
    cron_pg_dump: true
    server_names:
      - api.fortkentcinema.com
      - www.fortkentcinema.com          # NEW
      - fortkentcinema.com              # NEW
    media_root: "{{ deploy_base }}/api_fortkentcinema_com/shared/media/"
    nginx_extra_locations: |            # NEW block
        if ($host = fortkentcinema.com) {
            return 301 https://www.fortkentcinema.com$request_uri;
        }
    env_vars:
      # ... existing vars unchanged ...
      ALLOWED_HOSTS: api.fortkentcinema.com,www.fortkentcinema.com,fortkentcinema.com   # CHANGED
      USE_PROXY_HEADERS: "True"                                                          # NEW
      SECURE_SSL_REDIRECT: "True"                                                        # NEW
      SESSION_COOKIE_SECURE: "True"                                                      # NEW
      CSRF_COOKIE_SECURE: "True"                                                         # NEW
      CSRF_TRUSTED_ORIGINS: "https://www.fortkentcinema.com,https://fortkentcinema.com,https://api.fortkentcinema.com"  # NEW
      SECURE_HSTS_SECONDS: "31536000"                                                     # NEW
```

Notes on why this is the right shape, from reading the ansible roles:

- `django-site.conf.j2` (`roles/nginx/templates/django-site.conf.j2`)
  already renders `server_name {{ app.server_names | join(' ') }}` and a
  single `ssl_certificate .../{{ app.server_names[0] }}/...` — since
  `server_names[0]` stays `api.fortkentcinema.com`, the existing cert path is
  unaffected; certbot (below) just **expands** that same cert to cover the
  two new SANs.
- The apex→www redirect uses the exact same `nginx_extra_locations: if
  ($host = ...) { return 301 ...}` idiom already used by the
  `www_fortkentcinema_com` static entry (and by `cinema_sass`/
  `www_leprinceos_com`) — copied here so `fortkentcinema.com` still 301s to
  `www.fortkentcinema.com`, now served by Django instead of nginx `alias`ed
  static files.
- `roles/certbot/tasks/main.yml` obtains the cert if missing, or **expands**
  it (`certbot certonly ... --expand -d <server_names joined>`) if
  `/etc/letsencrypt/live/api.fortkentcinema.com/fullchain.pem` already
  exists — which it does. No manual certbot invocation needed; the ansible
  run handles it.
- `site.yml`'s `pre_tasks` filter `django_apps`/`static_sites` down to a
  single entry when `-e deploy_app=<name>` is passed, and **clear the other
  list entirely** when it doesn't match. That means a single
  `-e deploy_app=api_fortkentcinema_com` run will deploy the django app but
  do nothing to `static_sites` (including the one being deleted from the
  vars file) — the removal takes effect just by no longer being in
  `group_vars/webservers.yml`, not by any special "delete" step in the
  playbook. No separate destroy step is required; if you want the old
  static file tree cleaned off disk that's a manual `rm -rf` on the box
  (optional cosmetic cleanup, not required for cutover correctness).

## 4. Deploy (human-run; NOT executed by this task)

From the ansible repo, against the `webservers` inventory group:

```bash
ansible-playbook site.yml --tags deploy,nginx,certbot -e deploy_app=api_fortkentcinema_com
```

This single invocation (per `site.yml`'s task list, filtered to the one app
by the pre_tasks above) will:

1. Run the `django_app` role (`tags: deploy`): pull the merged branch,
   install/upgrade the shared venv (`requirements.txt`, now including
   `gunicorn==23.0.0`), run `manage.py migrate --noinput`, run
   `manage.py collectstatic --noinput`, and restart the `fortkentcinema`
   systemd/gunicorn service to pick up the new env vars.
2. Run the `certbot` role (`tags: certbot`): expand the existing cert to
   include `www.fortkentcinema.com` + `fortkentcinema.com`.
3. Run the `nginx` role (`tags: nginx`): re-render
   `/etc/nginx/sites-available/api_fortkentcinema_com` with the 3
   `server_name`s + the apex redirect block, validate with `nginx -t`, and
   reload nginx.

Because `deploy_app` filters `static_sites` to empty when it doesn't match,
this run will **not** touch the `www_fortkentcinema_com` static site role
invocation even before its entry is deleted — the entry removal in Section 3
is what makes the change durable for future full (`deploy_app`-less) runs.

## 5. Verification (human-run)

- [ ] `curl -I https://www.fortkentcinema.com/` returns `200` with a
      Django-rendered page (check for the `Server` header switching away
      from whatever nginx reports for static file serving, and confirm the
      HTML is the Django template output, not the old Vite `index.html`).
- [ ] `curl -s https://www.fortkentcinema.com/blog/<any-existing-slug>/ |
      grep -i 'og:'` shows per-post Open Graph tags (title, absolute
      `og:image`, `og:url`) — the SEO polish from Task 2.
- [ ] `curl -s https://www.fortkentcinema.com/sitemap.xml` and
      `.../robots.txt` both resolve (Task 1).
- [ ] `curl -I https://fortkentcinema.com/` returns a `301` to
      `https://www.fortkentcinema.com/`.
- [ ] `curl -I http://www.fortkentcinema.com/` (plain HTTP) redirects to
      HTTPS (confirms `SECURE_SSL_REDIRECT` + the nginx port-80 server block
      behave together).
- [ ] `curl -s https://api.fortkentcinema.com/api/posts/` still returns
      data — confirm the API host is unaffected by the nginx re-render
      (same file, additional `server_name`s only).
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

1. In `ansible/group_vars/webservers.yml`, re-add the
   `www_fortkentcinema_com` entry to `static_sites` (restore from git
   history / this runbook's Section 3a) and remove `www.fortkentcinema.com`
   + `fortkentcinema.com` (and the associated `nginx_extra_locations` block
   and the 4 new `env_vars`) from the `api_fortkentcinema_com` django_app
   entry, restoring `ALLOWED_HOSTS` to `api.fortkentcinema.com` only.
2. Re-run the nginx (and certbot, if the static site's cert had been
   allowed to lapse — unlikely across a short window) tag:
   ```bash
   ansible-playbook site.yml --tags deploy,nginx,certbot
   ```
   (omit `-e deploy_app=...` here so both the static site and the django
   app's nginx configs get re-rendered in one pass, or run it twice with
   `-e deploy_app=www_fortkentcinema_com` and
   `-e deploy_app=api_fortkentcinema_com`).
3. The React build under `{{ deploy_base }}/www_fortkentcinema_com` is not
   deleted by cutover (Section 3 notes the old static tree is left on disk
   unless manually removed), so the `static_site` role's re-run just
   re-links the existing build — no rebuild needed for an immediate
   rollback.
4. Verify `https://www.fortkentcinema.com/` serves the React `index.html`
   again and `https://fortkentcinema.com` still 301s to `www`.
