# Dashboard permissions

**Date:** 2026-10-21
**Status:** Approved design, awaiting plan

## Intent

Today every dashboard view is gated by one check: `request.user.is_staff`.
A staff account can see and change everything, from refunding ticket orders
to deleting blog posts. The owner wants each dashboard function to honour
Django's model permissions for the object it touches, so that a box-office
account, a programmer, or a marketing volunteer sees only what they are
allowed to see and can change only what they are allowed to change.

Decisions made with the owner:

- **Full CRUD.** Reading is enforced too: list and detail pages need `view`.
- **Home filters by permission.** The home page stays reachable for every
  staff user, but each card and alert renders only if the user can view
  the model behind it.
- **No preset groups.** The dashboard honours whatever permissions a user
  holds. The owner builds groups in Django admin (`/admin/`).
- **Child objects use their own model's permission.** Poll options, votes,
  tier benefits, membership terms, and free admissions check permissions
  on their own model, not on the parent page's model.

Out of scope: object-level (per-row) permissions, a permissions UI inside
the dashboard, and any change to the public site.

## The access mixin

`dashboard/mixins.py` keeps `StaffRequiredMixin` and its behaviour:
anonymous users go to login with `next=`, authenticated non-staff get 403.
It gains one attribute:

```python
class StaffRequiredMixin(AccessMixin):
    permission_required: str | tuple[str, ...] = ()
```

`dispatch` runs the staff check, then calls `has_dashboard_permission()`.
The default implementation returns `request.user.has_perms(...)` over the
declared permissions; a view may override it when the rule is not "all of
these" (the markdown preview accepts either of two). A failed check raises
`PermissionDenied`,
so the response is the same 403 non-staff already get. Superusers pass
through Django's own `has_perm` short-circuit; nothing in the dashboard
special-cases them.

When the request is HTMX (`HX-Request` header) the 403 response also sets
`HX-Trigger` with a `dashboard-toast` of kind `error` and message
"You don't have permission to do that." The existing toast bridge in
`dashboard.js` already listens for that event, so a stale tab fails
visibly rather than silently swapping nothing.

`HomeView` declares no permission: it needs only `is_staff`. Every other
dashboard view declares one. A test enforces this (see Testing).

## The permission map

The rule: a view requires the Django permission for the model it touches,
matching the action.

| Action kind | Permission |
|---|---|
| List, detail, CSV export, preview, PNG, audio stream, search | `view_<model>` |
| Create form and submit | `add_<model>` |
| Edit form and submit, status change, notes, allowance, retry, resend, refund, arrive, unarrive, retire or restore, announce, move | `change_<model>` |
| Delete | `delete_<model>` |

Per view:

### cinema

| View | Permission |
|---|---|
| ScreenListView | `cinema.view_screen` |
| ScreenCreateView | `cinema.add_screen` |
| ScreenEditView | `cinema.change_screen` |
| ScreenDeleteView | `cinema.delete_screen` |
| FilmSearchView | `cinema.view_film` |
| FilmSearchTMDBView, FilmFromTMDBView | `cinema.add_film` |
| EngagementListView, EngagementDetailView, EngagementSocialCardView | `cinema.view_engagement` |
| EngagementCreateView | `cinema.add_engagement` |
| EngagementEditView, EngagementStatusView, EngagementSquareRetryView | `cinema.change_engagement` |
| EngagementDeleteView | `cinema.delete_engagement` |
| ShowtimeCreateView, ShowtimeBulkView | `cinema.add_showtime` |
| ShowtimeEditView | `cinema.change_showtime` |
| ShowtimeDeleteView | `cinema.delete_showtime` |
| PollListView, PollDetailView, PollVotesExportView | `cinema.view_poll` |
| PollCreateView | `cinema.add_poll` |
| PollEditView, PollStatusView, PollAnnounceView | `cinema.change_poll` |
| PollDeleteView | `cinema.delete_poll` |
| PollOptionAddView | `cinema.add_polloption` |
| PollOptionMoveView | `cinema.change_polloption` |
| PollOptionRemoveView | `cinema.delete_polloption` |
| PollVoteRemoveView | `cinema.delete_vote` |
| RentalInquiryListView | `cinema.view_rentalinquiry` |
| RentalInquiryStatusView | `cinema.change_rentalinquiry` |
| AdInquiryListView | `cinema.view_adinquiry` |
| AdInquiryStatusView | `cinema.change_adinquiry` |

The engagement detail page embeds showtimes, so it needs `view_engagement`
only; the showtime rows' buttons check showtime permissions in the template.
`EngagementDetailView` and `PollDetailView` load the related rows regardless;
the template decides what to render.

### tickets

| View | Permission |
|---|---|
| ShowtimeOrdersView, ShowtimeOrdersExportView, TicketSummaryView, TicketOrderListView, TicketOrderLogExportView | `tickets.view_ticketorder` |
| ShowtimeAllowanceView | `cinema.change_showtime` |
| TicketOrderArriveView, TicketOrderUnarriveView, TicketOrderRetryView | `tickets.change_ticketorder` |
| ShowtimeRefundAllView, TicketOrderRefundView | `tickets.refund_ticketorder` (custom, declared in `TicketOrder.Meta.permissions`; added 2026-10-22) |

### audience

| View | Permission |
|---|---|
| MemberListView, MemberDetailView, MemberExportView | `audience.view_member` |
| MemberCreateView | `audience.add_member` |
| MemberEditView | `audience.change_member` |
| MemberDeleteView | `audience.delete_member` |
| TermLedgerView, TermExportView | `audience.view_membershipterm` |
| TermCreateView | `audience.add_membershipterm` |
| TermEditView | `audience.change_membershipterm` |
| TermDeleteView | `audience.delete_membershipterm` |
| FreeAdmissionRedeemView | `audience.add_freeadmission` |
| FreeAdmissionDeleteView | `audience.delete_freeadmission` |
| TierListView | `audience.view_membershiptier` |
| TierCreateView | `audience.add_membershiptier` |
| TierEditView, TierListingView | `audience.change_membershiptier` |
| TierDeleteView | `audience.delete_membershiptier` |
| BenefitCreateView | `audience.add_membershipbenefit` |
| BenefitEditView | `audience.change_membershipbenefit` |
| BenefitDeleteView | `audience.delete_membershipbenefit` |
| SubscriberListView, SubscriberExportView | `audience.view_subscriber` |

### boxoffice

| View | Permission |
|---|---|
| SquareSaleListView | `boxoffice.view_membershipsale` |
| SquareSaleRetryView | `boxoffice.change_membershipsale` |

### blog

| View | Permission |
|---|---|
| BlogListView, BlogPostPreviewView | `blog.view_blogpost` |
| BlogPostCreateView | `blog.add_blogpost` |
| BlogPostEditView | `blog.change_blogpost` |
| MarkdownPreviewView | `blog.add_blogpost` **or** `blog.change_blogpost` |
| BlogPostDeleteView | `blog.delete_blogpost` |
| AuthorCreateView / AuthorEditView / AuthorDeleteView | `blog.add_blogauthor` / `blog.change_blogauthor` / `blog.delete_blogauthor` |
| CategoryCreateView / CategoryEditView / CategoryDeleteView | `blog.add_blogcategory` / `blog.change_blogcategory` / `blog.delete_blogcategory` |

`MarkdownPreviewView` is the one view where either of two permissions is
enough. The mixin supports this with a hook, `has_dashboard_permission()`,
that a view may override; the default checks `permission_required` with
`has_perms`. The markdown preview overrides it to accept either.

### phone

| View | Permission |
|---|---|
| VoicemailListView, VoicemailAudioView | `phone.view_voicemail` |
| VoicemailStatusView, VoicemailNotesView | `phone.change_voicemail` |
| VoicemailDeleteView | `phone.delete_voicemail` |

### dashboard

| View | Permission |
|---|---|
| HomeView | none beyond `is_staff` |

## What the user sees

The server is authoritative: a hidden control's URL still answers 403.
Templates hide controls only so staff are not shown buttons that fail.
Templates use Django's `perms` context variable, already provided by the
auth context processor, as `{% if perms.cinema.add_screen %}`.

### Sidebar

Each link in `_sidebar.html` renders only with the `view` permission for
its section's model. Home is always present. Mapping:

| Link | Permission |
|---|---|
| Ad Inquiries | `cinema.view_adinquiry` |
| Blog | `blog.view_blogpost` |
| Engagements | `cinema.view_engagement` |
| Members | `audience.view_member` |
| Memberships | `audience.view_membershiptier` |
| Online tickets | `tickets.view_ticketorder` |
| Polls | `cinema.view_poll` |
| Rental Inquiries | `cinema.view_rentalinquiry` |
| Screens | `cinema.view_screen` |
| Subscribers | `audience.view_subscriber` |
| Voicemails | `phone.view_voicemail` |

The new-voicemail badge, and the `new_voicemail_count` tag that feeds it,
render only when the link does.

Pages reached from inside another page rather than from the sidebar follow
the same rule in the page that links to them: the terms ledger link
(`audience.view_membershipterm`), Square sales (`boxoffice.view_membershipsale`),
the showtime orders link on a showtime row (`tickets.view_ticketorder`).

### Keyboard hint

The "Alt+N New Engagement" hint in `base_dashboard.html`, and the keyboard
handler it describes, render only with `cinema.add_engagement`.

### Page controls

Every control that calls a mutating or export view is wrapped in the
permission check of the view it calls. This covers: New buttons in page
headers, Edit and Delete buttons in table rows and cards, status dropdowns,
notes forms, retry and refund buttons, arrive and unarrive buttons,
retire/restore, redeem, option add/remove/move, vote remove, announce,
export CSV links, social card download buttons, and the empty-state
"Add your first…" buttons.

When a user can view a list but has no permission for any row action, the
Actions column header and the actions cell render empty rather than being
removed, so table layouts stay aligned with no new CSS.

The blog page's Authors and Categories panels render only with
`blog.view_blogauthor` and `blog.view_blogcategory`.

### Home

`HomeView` passes the user to the context builders and filters:

| Element | Permission to render |
|---|---|
| Active Engagements card | `cinema.view_engagement` |
| Today's Showtimes card and table | `cinema.view_showtime` |
| Screens card | `cinema.view_screen` |
| Yesterday's Sales card | `boxoffice.view_salespull` |
| "View Engagements" link in the empty state | `cinema.view_engagement` |

Smart alerts: `build_smart_alerts` adds a `perm` key to every alert it
builds; `HomeView` drops alerts whose `perm` the user lacks. Mapping:

| Alert id | Permission |
|---|---|
| no-showtimes-tomorrow | `cinema.view_showtime` |
| ending-soon-*, draft-engagements | `cinema.view_engagement` |
| new-rental-inquiries | `cinema.view_rentalinquiry` |
| new-ad-inquiries | `cinema.view_adinquiry` |
| new-voicemails | `phone.view_voicemail` |
| square-pull-failed, -missing, -incomplete | `boxoffice.view_salespull` |
| square-sync-failed | `cinema.view_engagement` |
| square-membership-failed | `boxoffice.view_membershipsale` |
| ticket-failures, nearly-sold-out-*, cancelled-orders-* | `tickets.view_ticketorder` |

The queries behind a hidden element are skipped too, where that is cheap
to do (the inquiry counts, the voicemail count, the Square statuses).

## Testing

### Helpers

A new `dashboard/tests/helpers.py`:

- `DASHBOARD_PERMISSIONS`: the set of every `app.codename` named in this
  spec, built from the view classes at import time so it cannot drift.
- `make_staff(username="staffer", password="pw12345", perms=ALL)`: creates
  an `is_staff` user holding the given permissions. `ALL` grants
  `DASHBOARD_PERMISSIONS`; a tuple grants only those.

### Existing tests

The 30 test files that create `is_staff=True` users switch to
`make_staff()` with full permissions, so current behaviour stays covered
and the suite stays green through the change. Tests that build a
non-staff user keep doing so by hand.

### New tests

- `test_auth.py`: no permission gives 403; HTMX request without permission
  gives 403 with the toast `HX-Trigger`; superuser without explicit
  permissions passes; a view with a tuple requires every permission.
- `test_permission_map.py`: a table of `(url name, kwargs, method,
  permission)` covering every dashboard URL except home. For each row, a
  staff user with every permission except that one gets 403, and a user
  with only that permission does not get 403. A separate test walks
  `dashboard.urls.urlpatterns` and asserts each view class except
  `HomeView` declares a non-empty `permission_required` or overrides
  `has_dashboard_permission`, so a new view cannot ship unguarded.
- `test_markdown_preview` gains: `add_blogpost` alone passes,
  `change_blogpost` alone passes.
- Template tests, one per list page: a user with `view` only sees the
  rows but none of the Edit, Delete, or New controls; a user with `add`
  sees New but not Edit.
- `test_home.py`: a user with only ticket permissions sees the showtimes
  table and ticket alerts, and does not see the voicemail alert, the
  Screens card, or the Engagements card; the sidebar for that user shows
  Home and Online tickets only.

## Documentation

README gains a short "Granting dashboard access" section: a dashboard
user needs Staff status, and sees only the sections they hold `view`
permission for; permissions and groups are managed in Django admin.
Superusers see everything.

## Not changing

- No new models, migrations, or settings.
- No preset groups.
- The public site, the Twilio webhooks, the Square webhook, and management
  commands are untouched.
- The login page and `LOGIN_URL` are untouched.
