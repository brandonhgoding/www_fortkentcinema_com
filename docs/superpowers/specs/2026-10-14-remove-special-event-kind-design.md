# Remove the Special Event kind from Engagement — design

Decided 2026-10-14. Events are leaving `Engagement` so they can become a
model of their own in later work. This spec covers only the removal: the
engagement starts clean, and nothing here anticipates the shape of the
new model.

---

## Decided

| | | Why |
|---|---|---|
| **`Kind.SPECIAL_EVENT`** | Removed. Existing rows become `REGULAR` first. | Events will be their own model. Nothing on the public site filters on this kind except the Heckle Night lineup, which is being rebuilt against the new model anyway. |
| **`event_title`** | Renamed to `display_title`. Same type, same length, still optional. | The field was never event-specific: the dashboard offered it for Classics and Double Features too, and its placeholder is "Creature Double Feature". The name now says what it does. |
| **`show_in_main_listings`** | Stays as is. | It is the only privacy guard for private bookings, read by Now Showing, the phone line and Heckle Night. It is unrelated to the kind. |
| **`default_visibility_for(kind)`** | Removed. | Dead code. Nothing calls it; it existed to say "non-Regular kinds hide by default", which the form never honoured. |
| **Fallback title property** | Renamed from `display_title` to `title`. | The field takes the name `display_title`, so the property that returns the override-or-film-titles needs a new one. `engagement.title` reads naturally at every call site. |
| **Heckle Night lineup** | Returns nothing for now. The page keeps its dates and reads "Not booked yet" on every row. | The lineup query was "the 7:00 PM Special Event on the third Friday". With the kind gone it has nothing to match. Work landing later today wires it to the new Event model; an interim title-suffix match would be thrown away within hours. |
| **Title suffix parsing** | Untouched. | Staff still type "(Heckle Night)" into the title and Coming Soon still normalises it. That goes when the new model gives them a better handle, not before. |

## Migrations

Two migrations in `cinema`, in this order:

1. **`0025_special_event_to_regular`** — data migration. Every
   `Engagement` with `kind="SPECIAL_EVENT"` is updated to
   `kind="REGULAR"`. Reverse is a no-op: once the rows are Regular nothing
   can tell which ones used to be events, and inventing that would be
   worse than leaving it.
2. **`0026_remove_special_event_rename_display_title`** — schema. Alters
   the `kind` choices to drop Special Event, and renames `event_title` to
   `display_title`. `RenameField` keeps the data; no copy step is needed.

The data migration runs first so the choice list never excludes a value
still present in the table. Django does not enforce choices at the database
level, but a migration test should not have to rely on that.

## Model

`cinema/models/engagement.py`:

- `Kind` becomes `REGULAR`, `CLASSIC`, `DOUBLE_FEATURE`.
- `display_title = CharField(max_length=200, blank=True)` replaces
  `event_title`.
- `title` property: `display_title` when set, otherwise the ordered film
  titles joined with `" + "`. This is the old `display_title` property
  under its new name, unchanged in behaviour.
- `__str__` uses `title`.
- `default_visibility_for` is deleted.

Every reader of the old property moves to `title`. Known call sites, from
a grep on 2026-10-14: `boxoffice/sync.py`, `boxoffice/spec.py`,
`cinema/admin.py` (`list_display`), `cinema/models/showtime.py`,
`cinema/showtimes_overlap.py`, `cinema/social_cards/card.py`,
`dashboard/smart_alerts.py`, `dashboard/views.py`, the dashboard
`home.html`, `_social_cards.html`, `_engagement_list.html` and
`engagement_detail.html` templates, `phone/speech.py`,
`web/services/cinema_data.py` (Coming Soon), and
`web/services/heckle_night.py`. The implementation plan should grep for
`display_title` and `event_title` across the repo rather than trust this
list.

## Dashboard

- `KIND_OPTIONS` in `dashboard/forms.py` and `KIND_LABELS` in
  `dashboard/views.py` drop Special Event.
- `EngagementForm.Meta.fields` lists `display_title` in place of
  `event_title`. Placeholder text stays.
- `_engagement_form.html`: the field is labelled "Display title" and is
  shown for every kind. The `x-show="kind !== 'REGULAR'"` wrapper goes.
  The Alpine component has no Special Event logic and needs no change.
- `_engagement_list.html`: unchanged in structure; the kind badge still
  shows for non-Regular kinds, which are now Classic and Double Feature.
- `engagement_detail.html`: the "Event:" row becomes "Display title:" and
  still appears only when the override is set and differs from `title`.

## Heckle Night

`web/services/heckle_night.py`:

- `heckle_showtimes(dates)` returns `{}` unconditionally. Its docstring
  says why in two sentences and names the Event model as the replacement.
  The query body is removed rather than left behind a flag, so there is no
  dead branch to keep in sync.
- `upcoming_nights`, `third_friday` and `get_heckle_nights` are unchanged.
  Every row renders with `film=None`, which the template already handles
  as "Not booked yet".
- The module docstring and the `HECKLE_NIGHT` comment in `web/constants.py`
  that describe the Special Event filter are trimmed to describe the
  interim state. The "start_time is matched exactly" comment stays, since
  the exact-time rule is expected to survive into the new lookup.

## Tests

Fixture changes, mechanical:

- Every helper that passes `kind="SPECIAL_EVENT"` or
  `Engagement.Kind.SPECIAL_EVENT` passes `REGULAR` instead. Known:
  `web/tests/test_event_titles.py`, `web/tests/test_heckle_night.py`.
- Every fixture that sets `event_title=` sets `display_title=`. Known:
  `boxoffice/tests/test_sync.py`, `boxoffice/tests/test_spec.py`,
  `cinema/tests/test_models.py`, `cinema/tests/test_social_cards_card.py`,
  `dashboard/tests/test_smart_alerts.py`,
  `dashboard/tests/test_engagements.py`,
  `dashboard/tests/test_square_views.py`, `web/tests/test_cinema_data.py`,
  and any form payloads that post `"event_title"`.
- Every assertion on the old `display_title` property asserts on `title`.

Behaviour tests, new or rewritten:

- **Model.** `title` returns the override when `display_title` is set and
  the joined film titles otherwise. `"SPECIAL_EVENT"` is not among
  `Engagement.Kind.values`. `Engagement` has no attribute
  `default_visibility_for`.
- **Migration.** A plain `TestCase` creates an engagement with
  `kind="SPECIAL_EVENT"` against the final schema (choices are not
  enforced by the database), calls `0025`'s `special_event_to_regular`
  function directly, and asserts the row is `kind="REGULAR"` with its
  title intact and a Classic row untouched. The migration executor is
  avoided on purpose: a `TransactionTestCase` flushes every table on
  teardown, which wipes the seeded audience catalogue other tests rely on.
  `RenameField` is Django's and is not re-tested.
- **Heckle Night.** The lineup tests that booked a Special Event and
  expected a film (`test_booked_night_carries_its_film`,
  `test_a_special_event_is`, `test_seven_oclock_on_the_nose_is`,
  `test_the_regular_feature_does_not_win_over_the_event`) become a single
  test that a confirmed, listed 7:00 PM third-Friday booking is **not**
  claimed. Tests that already assert a night is not claimed stay and now
  pass trivially. `test_no_other_kind_counts_either` loses its
  Special Event reference. `test_query_count_does_not_grow_with_the_number_of_nights`
  still holds: zero queries do not grow either.
- **Dashboard.** Posting `"kind": "SPECIAL_EVENT"` to the engagement form
  is rejected as an invalid choice. The display title field renders for a
  Regular engagement.
- **Event titles.** `web/tests/test_event_titles.py` keeps every
  suffix-parsing test. `test_heckle_page_drops_the_suffix` is removed, since
  the page no longer shows a film. `test_coming_soon_normalises_the_suffix`
  and `test_the_stored_title_is_untouched` stay, the latter reading
  `.title`.

## Out of scope

- Historical specs that mention `SPECIAL_EVENT` or `event_title` are left as
  written. They describe decisions at the time they were made.
- The `"craft night"` entries in `web/services/titles.py` `EVENT_NAMES`
  stay, even though Craft Night is gone.
- The footer Events column, `llms.txt`, the Open Mic page and
  `RentalInquiry.event_type` do not change. None of them touch
  `Engagement`.
- Nothing about the new Event model is designed here.

## Unknowns

The local database holds no engagements, so the production count of
Special Event rows and private bookings is unknown. The data migration is
correct at any count. If production has Special Event rows that are hidden
private bookings, they stay hidden, since `show_in_main_listings` is not
touched.
