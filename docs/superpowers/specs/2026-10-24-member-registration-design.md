# Member registration with email verification

Date: 2026-10-24. Status: approved in conversation, awaiting spec review.
Supersedes `2026-10-24-member-magic-link-design.md`: the owner switched
members back to password sign-in after the magic-link build was reviewed.

## Why

The members' area (see `2026-10-23-email-login-design.md`) needs member
accounts before member voting and the member ticket rate. A member
account stores an email and a password hash and nothing else. Members
register with a password, then confirm their address by emailed link.

## Decisions (owner, 2026-10-24)

- **Passwords for everyone.** One email + password sign-in for staff and
  members. No magic-link sign-in.
- **Register, then verify.** Registering asks for an email and a password;
  the account exists at once but cannot sign in until the address is
  confirmed by link.
- **Verification links last 24 hours** and work once.
- **Accounts never verified are deleted after 7 days** by a nightly job.
- **Anyone may register.** An account whose email matches a roster
  `audience.Member` shows that membership on the member home.
- **Members land on `/dashboard/`**, which shows them a member home; every
  staff page stays staff-only. (Built on the branch; unchanged.)
- **Throttles, said plainly:** one email per address per 5 minutes, and
  at most 5 registration or resend requests per IP per hour.

## Data

- `accounts.User` gains `email_verified_at = DateTimeField(null=True,
  blank=True)`. Migration `accounts 0004` adds it and marks every
  existing user verified (`email_verified_at = now`), so staff are
  unaffected.
- Verification is required only for non-staff accounts. Staff are made
  in the admin as today and never asked to verify.
- A registered, unverified member is `is_active=True`,
  `email_verified_at=None`, with a usable password.

## Flow

### 1. Registering (`/register`)

Linked from `/login` as "Create an account". The form: email, password,
password again, and the hidden `website` honeypot. Passwords must pass
`AUTH_PASSWORD_VALIDATORS` (errors shown on the form). In order:

1. **Honeypot** filled → the "check your email" page, nothing stored or
   sent. Checked before validation.
2. **Invalid form** (bad email, mismatched or weak password) → the form
   again with errors.
3. **Per-IP cap.** More than 5 registration or resend requests from one IP
   in an hour → "Too many requests from this connection. Try again later."
   (status 429), nothing stored or sent.
4. **Per-address throttle.** If this address was emailed in the last 5
   minutes → "We sent an email to this address in the last 5 minutes.
   Check your inbox (and spam), or try again after 7:42 PM." Nothing
   stored. The throttle counts the address whether or not an account
   exists.
5. Otherwise, by what exists for the address:
   - **nothing:** create the unverified member with this password; email
     a verification link;
   - **unverified member:** set this password; email a fresh link;
   - **verified account, or a staff account:** change nothing; email
     "You already have an account. Sign in or reset your password," with
     links to `/login` and `/password-reset`;
   - **inactive (closed) account:** change nothing, send nothing.

   Every case shows the same page: "Check your email to confirm
   your address", naming the address.

### 2. The verification link

`/register/verify/<token>`: a `django.core.signing` timestamped
signature (salt `accounts.verify-email`) over the user's pk and email,
valid 24 hours. It is usable only while that user still exists, still
has that email, is active, non-staff and unverified, so confirming spends
it (and any other link still out for that account).

`GET` shows "Confirm your email, name@example.com" with a password field
and a "Confirm my email" button and changes nothing, so a mail scanner
fetching the link cannot verify an account someone else registered with
that address. The password field is there because anyone can re-register
an unverified address after the throttle (which sets a new password) and
older links stay usable: without it, an attacker's password could end up
on an account the owner verifies, or the reverse. `POST` re-checks the
token and that the password matches the account's current one (otherwise
it shows the confirm page again with an error and verifies nothing; the
latest registrant's password is the one that works), then sets `email_verified_at`, and shows "Email
confirmed. You can sign in now." with a link to `/login`. It does not
sign the person in: signing in with the password proves they registered.
An unusable token shows "This confirmation link has expired or was
already used." with a link to `/login` to request a new one (status
410). The submit button disables itself on click. Both responses are
`never_cache`.

### 3. Signing in (`/login`)

One form: email and password, "Sign in", "Forgot password?", and "Create
an account" → `/register`. The magic-link form and staff toggle are
gone. A signed-in visitor opening `/login` without `?next=` is sent to
`/dashboard/`.

A member whose password is correct but whose email is unverified is not
signed in and sees "Please confirm your email first. We can send a new
link." with a "Send a new link" button. That posts to `/register/resend`,
which applies the same honeypot, per-IP cap and per-address throttle,
emails a fresh link if the account is still an unverified member, and
shows the "check your email" page. Only someone who knows the password
sees this message, so it reveals nothing to others.

Wrong passwords, axes lockout and "Forgot password?" behave as today, for
staff and members alike. A member who resets their password through the
reset flow is also marked verified (the reset link reached their inbox).

### 4. Cleanup

Management command `delete_unverified_accounts` deletes non-staff users
with `email_verified_at` null and `date_joined` more than 7 days ago, and
prints how many. The ansible `django_app` role gets an optional nightly
cron (`cron_unverified_cleanup`, 3:15 AM Eastern, `flock`, like
`cron_ticket_expire`), enabled for this site. The ansible edit is left
uncommitted for the owner.

### 5. Client IP

`accounts.client_ip.request_ip(request) -> str | None` is the one source
of the visitor's address. With `USE_PROXY_HEADERS` on (production: nginx
in front of a gunicorn unix socket, where `REMOTE_ADDR` is empty) it
returns `X-Real-IP`, which nginx's `proxy_params` sets from the address
it saw, overwriting anything the client sent; otherwise `REMOTE_ADDR`.
Empty → `None`, which the per-IP cap does not count. Settings point
`AXES_CLIENT_IP_CALLABLE` at it and drop the `AXES_IPWARE_*` lines, which
did nothing because django-ipware is not installed. This also makes axes
lockout key on the real IP again for staff.

## Emails

Plain text, like the password-reset email.

- Verify: subject "Confirm your Fort Kent Cinema account"; the link; that
  it works once and expires in 24 hours; ignore it if you didn't sign up.
- Already registered: subject "Your Fort Kent Cinema account"; you
  already have an account; links to sign in and reset the password;
  ignore it if you didn't try to sign up.

A send failure is logged and the visitor still sees the "check your
email" page.

## Kept from the magic-link branch

The member home and member sidebar, the footer "Member sign in" and the
membership-page line (both → `/login`), the throttle helpers
(`claim_address`, the per-IP counter) and the `MagicLinkForm` honeypot
pattern, renamed for registration. The magic-link sign-in view, token,
templates and tests are removed.

## Testing

- Registration: honeypot first; invalid email, mismatched and weak
  passwords; new address creates an unverified member with a usable
  password and sends one verify email; unverified address resets the
  password and resends; verified member and staff addresses get the
  "already registered" email and are unchanged; inactive gets nothing;
  same page in every case; per-address throttle message with the exact
  time; per-IP cap 429 after 5.
- Verification: GET changes nothing; POST with the right password verifies, with none or a wrong one it does not (and the link stays usable); an attacker's re-registration cannot be confirmed with the owner's old password; second POST, expired
  (24 h + 1 s), tampered, deleted user, changed email and staff token all
  410; button disables on click; never_cache headers.
- Sign-in: unverified member with the right password is not signed in and
  sees the resend button; wrong password still says "Invalid email or
  password."; verified member signs in to `/dashboard/`; staff unchanged
  (lockout, `next`); signed-in user on `/login` is redirected; resend
  sends a fresh link and is throttled.
- Reset marks a member verified.
- Cleanup command deletes only unverified non-staff older than 7 days.
- `request_ip`: production shape (`REMOTE_ADDR=""`, `X-Real-IP` set)
  gives distinct buckets per visitor; a forged `X-Forwarded-For` changes
  nothing; without proxy headers it uses `REMOTE_ADDR`; axes uses it.
- Migration 0004 marks existing users verified.
- Headless screenshots of `/login`, `/register` and the confirm page at
  desktop and phone widths.

## Out of scope

Member voting, the member ticket rate, sending email off the request
thread (timing differences between address kinds are accepted, bounded
by the throttles), a shared throttle store, and whether axes keeps its
access log for members (left to the owner).
