# Member sign-in by magic link

Date: 2026-10-24. Status: approved in conversation, awaiting spec review.

## Why

The members' area (see `2026-10-23-email-login-design.md`) needs member
accounts before member voting and the member ticket rate can follow. The
owner wants to store as little personal data as possible, so a member
account is an email address and nothing else: no name, no phone, no
password. Members sign in by an emailed link; registering is simply the
first sign-in.

## Decisions (owner, 2026-10-24)

- **Magic links for members, passwords for staff.** Staff keep the email
  and password sign-in, lockout and reset they have today.
- **Anyone may sign in.** An account whose email matches a roster
  `audience.Member` shows that membership; any other account still works.
- **Members land on `/dashboard/`**, which shows them a member home.
  This reverses the 2026-10-23 note that the members' area sits outside
  the dashboard. Every staff page stays staff-only.
- **One login screen.** `/login` leads with the email-me-a-link form and
  keeps the staff password form behind a toggle.
- **Sessions last 2 weeks** for members, the same as staff (Django's
  default; no separate rule).
- **Throttling, said plainly.** One link per address per 5 minutes, and
  the page says so when it refuses. At most 5 link requests per IP per
  hour.

## Flow

### 1. Asking for a link (`/login`)

The page shows an email box and a primary button, "Email me a sign-in
link". Beneath it, "Staff: sign in with password" reveals the existing
password field and its "Sign in" button; the password form posts exactly
as today (`EmailAuthenticationForm`, axes lockout, "Forgot password?").

The link form posts to `/login/link`. In order:

1. **Honeypot.** A filled-in hidden `website` field gets the normal
   "Check your email" page and no email, as on the site's other forms.
2. **Invalid email.** The form is redisplayed with the field error.
3. **Per-IP cap.** More than 5 link requests from one IP in an hour
   (counted with `cinema.voting.client_ip`) shows: "Too many sign-in
   requests from this connection. Try again later." No email is sent.
4. **Per-address throttle.** If this address was sent a link in the last
   5 minutes, the page shows: "We sent a sign-in link to this address in
   the last 5 minutes. Check your inbox (and spam), or try again after
   7:42 PM." The time is when the 5 minutes run out, in the cinema's
   timezone. The throttle counts the address whether or not an account
   exists, so this message reveals nothing about who has an account.
5. **Otherwise** the address is recorded for throttling and the page
   shows "Check your email" with the address. A link is emailed only if
   the address has no account or a non-staff, active account. A staff
   address, or an inactive account, gets the same page and no email.

Both counters live in the default cache, like the password-reset
throttle. That cache is per process, so with several server processes
the limits are approximate (a sender may get a few more than the cap);
this is enough to stop flooding and is accepted.

### 2. The link

`/login/link/<token>`, where the token is a `django.core.signing`
timestamped signature (salted for this purpose) over the email and the
account's `last_login` (empty when there is no account). It is valid for
`PASSWORD_RESET_TIMEOUT` (5 minutes) and only while the account's
`last_login` still matches, so the first successful sign-in, or creating
the account, makes the link spent.

### 3. Opening the link

`GET` never signs anyone in, so email scanners that follow links do not
spend them. A valid token shows "Sign in as name@example.com" with a
button. An expired, spent or tampered token, or an inactive or staff
account, shows "This sign-in link has expired or was already used" with
the email box to ask for a new one. A visitor already signed in is
redirected to `/dashboard/`.

`POST` re-checks the token, then:

- **no account:** creates `accounts.User(email=..., is_staff=False)`
  with an unusable password;
- signs the user in (`django.contrib.auth.login` with `ModelBackend`),
  which updates `last_login` and spends the link;
- redirects to `/dashboard/`.

A member account never gets a password. `PasswordResetForm` already
skips accounts with an unusable password, so the reset form cannot give
one to a member; a test pins this.

### 4. The email

Plain text, like the password-reset email. Subject: "Your Fort Kent
Cinema sign-in link". Body: the link, that it works once and expires in
5 minutes, and that it can be ignored if they did not ask for it. A
send failure is logged and the visitor still sees "Check your email".

## Member home in the dashboard

`HomeView` lets in any signed-in, active user. Staff see today's home,
unchanged. Non-staff see `dashboard/member_home.html`:

- their email;
- if a roster `Member` has the same email: tier, status label, covered
  through date, and free admissions used this month out of the
  allowance, computed with the same helpers the staff members list uses;
- otherwise: "No membership on file for this email. Join at the box
  office before any show," linking to `/membership/`.

The account is matched to the roster by email on each request; nothing
links them in the database, so a corrected roster email is followed
automatically.

Members get a member sidebar: logo, "powered by", LeprinceOS, **Home**,
and their email with Log out. Staff navigation is not rendered for
non-staff at all. Every other dashboard view keeps `StaffRequiredMixin`,
so a member reaching a staff URL gets the 403 page. The mobile header is
the same for both.

Log out goes to `/login`, as for staff.

## Links to it

- Footer, Explore column: "Member sign in" → `/login`.
- Membership page, under the note beneath the tiers: "Already a member?
  Sign in to see your membership." → `/login`.

`/login` is already `noindex` and disallowed in robots.txt; the new
`/login/link...` URLs sit under it.

## Data and rollout

No schema change: member accounts are `accounts.User` rows with
`is_staff=False` and an unusable password, created only when a link is
used, so unconfirmed or mistyped addresses are never stored. The feature
depends on outgoing email (Proton SMTP), which password reset already
needs. Built on its own branch; merged and pushed when the owner says;
the owner deploys.

## Testing

TDD with the existing test helpers. Cover:

- link form: honeypot, invalid email, same page for unknown, member,
  staff and inactive addresses, and email sent only for unknown or member
  addresses;
- per-address throttle message with the retry time, also for unknown
  addresses; per-IP cap message after 5 requests in an hour;
- token: valid, expired after 5 minutes, spent after sign-in, spent after
  account creation, tampered, staff account refused;
- GET shows the button and signs nobody in; POST creates the account only
  then, with an unusable password, and signs in;
- password reset sends nothing to a member account;
- member home with and without a roster match; member gets 403 on a
  staff page; member sidebar has no staff links; staff home unchanged;
- footer and membership-page links;
- headless browser check of `/login` and the member home at desktop and
  phone widths.

## Out of scope

Member voting, the member ticket rate, passkeys or two-step codes, a
shared (cross-process) throttle store, and any change to staff sign-in.
