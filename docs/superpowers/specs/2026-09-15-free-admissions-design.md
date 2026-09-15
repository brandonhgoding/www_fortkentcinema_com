# Free Admissions — a monthly allowance per tier, and a record of every redemption — Design

**Date:** 2026-09-15
**Status:** Awaiting user review (design phase)
**Repo:** `api_fortkentcinema_com` (branch: `feat/free-admissions`)
**Builds on:** `docs/superpowers/specs/2026-09-13-membership-tier-catalogue-design.md`

## Context

Some membership tiers include free admissions each month — Cinema Supporter one,
Family Plus four. Nothing in this application knows that, so the allowance lives in
whoever is at the counter's head, and there is no way to answer either of the two
questions that matter: *has this member already used this month's?* and *how many
free admissions did we give away?*

The tier catalogue moved into the database on 2026-09-13, so a per-tier allowance is
now a field a staff member can edit rather than a constant requiring a deploy. This
adds that field, and a record of each redemption.

### Explicitly out of scope

- **A box-office lookup screen.** The 2026-09-11 membership design deferred a
  counter-optimised search, and that is still deferred. The roster's filter box is
  what staff use.
- **Linking a redemption to a showtime or film.** A redemption records the member and
  the date. Knowing *which* films members watch is a different question, and asking
  the counter to pick a screening from a list buys that answer with friction on every
  transaction. A nullable `showtime` FK can be added later without disturbing a single
  existing row.
- **Rollover.** An unused month is gone. Nobody asked for banking, and a bank turns
  "has she used September" into "what is her balance", which is a different feature.
- **Per-household sub-members.** Family tiers stay honour-system, as they already are;
  only the cardholder is stored, and the household's four admissions attach to them.
- **Member-facing anything.** No logins, no self-serve balance, no email.
- **A reporting screen.** See "One deliberate inclusion" below for the one number that
  is cheap enough to be worth having anyway.

## Decisions

### The allowance resets on the 1st, not on the membership anniversary

A member who joins on 15 March gets their second free admission on 1 April, not
15 April.

The alternative — a window running from the term's start day — is strictly fairer, but
it puts every member on a different cycle, so the box office cannot answer "has she
used this month's?" without first working out which window today falls in. Calendar
months make that one question with the same answer shape for everyone, and make "free
admissions given in August" a single date-range count.

The cost is that someone joining on the 28th gets a nearly-free month. That is a small
giveaway, in the member's favour, on a membership they just paid for.

### A redemption is a member, a date, and who recorded it

Nothing else. This is the minimum that answers both real questions, and it keeps the
counter interaction to one click.

`recorded_by` exists because a free admission is a small giveaway of the cinema's
money, and "who let this happen" is a question that gets asked eventually. It is
nullable and `SET_NULL`: removing a staff account must not delete the history of what
they did.

### Going over the allowance warns, and then allows

A two-screen cinema runs on the judgement of whoever is at the counter. A hard block
guarantees that the one time there is a good reason to say yes, the software says no,
and the workaround — editing records afterwards — is worse than the thing it prevents.

So the screen shows "September: 1 of 1 used", the button asks for confirmation, and
the extra redemption is recorded like any other. Because it is recorded, generosity
stays countable rather than becoming invisible.

There is deliberately **no uniqueness or check constraint** in the database. The
allowance is a policy, not an invariant, and encoding it as an invariant would make the
supported workflow impossible.

### Allowance is derived from the current term's tier

Not stored on the member, and not stored on the redemption.

`Member.current_term` already resolves the term covering today, and a term already
points at its tier. A member with no current term — lapsed — has an allowance of zero,
which is correct: the benefit came with the membership.

This means a tier granting zero and a lapsed member both render as `—` rather than
`0/0`. "Nothing to see here" is the same statement in both cases.

### Past months are shown against today's allowance

If Family Plus later changes from four to six, August will render as "4 of 6 used".

The fix would be snapshotting the allowance onto each redemption, which buys historical
accuracy and costs a field that is wrong the moment someone corrects a typo in a tier —
and correcting typos is now easy, because tiers are admin-editable. Given the choice
between a display that drifts when policy changes and a stored number that drifts when
anyone fixes anything, the derived version is the safer wrong.

The count of redemptions — the number that actually matters for "what did we give
away" — is exact either way.

### Deleting a member deletes their redemptions

`on_delete=CASCADE`, matching `MembershipTerm.member`, which already behaves this way
while carrying `price_paid`.

This does mean deleting a member silently changes past monthly totals. The alternative
is a second, contradictory rule about what member deletion means in this app. One rule
that is occasionally lossy beats two rules that disagree.

## Data model

### `MembershipTier` gains one field

```python
    free_admissions_per_month = models.PositiveSmallIntegerField(
        default=0,
        help_text="Free admissions this tier includes each calendar month. "
                  "0 means none. Resets on the 1st; unused ones do not carry over.",
    )
```

A data migration sets **Cinema Supporter 1** and **Family Plus 4**. The other three
tiers stay at 0.

> **Confirm before implementation:** Silver Screen, Individual and Family are assumed
> to include no free admissions. If any of them do, say so and the migration sets it.
> Either way the value is editable in the admin afterwards without a deploy, which is
> exactly what the 2026-09-13 catalogue work bought.

### `audience/models/free_admission.py`

```python
class FreeAdmission(models.Model):
    """One free admission, given to one member, on one day.

    Deliberately not linked to a showtime: the counter records that the
    benefit was used, not what was watched. There is no constraint stopping
    a member exceeding their tier's monthly allowance — that is a policy the
    UI warns about and staff may override, not an invariant.
    """

    member = models.ForeignKey(
        "audience.Member", related_name="free_admissions", on_delete=models.CASCADE
    )
    redeemed_on = models.DateField(default=timezone.localdate)
    note = models.TextField(blank=True)
    recorded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="+",
        help_text="Cleared rather than deleted if the staff account goes away.",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-redeemed_on", "-created_at"]
        verbose_name = "Free admission"
        verbose_name_plural = "Free admissions"
```

`redeemed_on` defaults to `timezone.localdate` — the callable, not a computed value, so
it is evaluated per row rather than frozen at import.

### Derived helpers on `Member`

```python
    @property
    def free_admission_allowance(self) -> int:
        """This member's monthly allowance, or 0 if they have no current term."""

    def free_admissions_in(self, year: int, month: int) -> int:
        """How many redemptions fall in that calendar month."""
```

`free_admission_allowance` reads through `current_term`, which iterates the prefetched
`terms` rather than querying — so it costs nothing extra on a roster that already does
`prefetch_related("terms__tier")`.

## Staff surface

### Roster (`/dashboard/members`)

A **Free this month** column showing `used / allowance`, and a Redeem button on rows
where the allowance is above zero. Rows with no allowance show `—` and no button.

The count comes from annotating the roster queryset:

```python
Count("free_admissions", filter=Q(redeemed_on__range=(first_of_month, last_of_month)))
```

one query for the whole page, applied **before** `member_roster` materialises the
queryset with `list()` for its Python-side status filtering.

Redeeming is an `hx-post` that swaps the list out of band and fires the existing
`HX-Trigger` toast, exactly as the delete buttons already do. When the member is
already at or over their allowance, the button carries a `data-dashboard-confirm`
payload — the same declarative confirmation the delete buttons use — naming the count
so the person clicking knows what they are approving.

### Member detail (`/dashboard/members/<pk>`)

A **Free admissions** panel listing redemptions grouped by calendar month, newest
first, each showing the date and who recorded it, with the month's header reading
"September 2026 — 2 of 4 used".

Each row has a delete, following the term-delete pattern, because staff will mis-click
and the fix should not require the Django admin.

### One deliberate inclusion

The roster header gains a single line: "September: 7 free admissions given". It answers
the second of the two real questions without a reporting screen.

**It counts the whole cinema's month and ignores the `?q=` and `?status=` filters.** It
is a house figure, not a total of the rows on screen — filtering the roster to one
surname must not make it look like the cinema gave away one free admission this month.
The label says "September", not "these members", for the same reason. This makes it one
extra aggregate query rather than a free by-product of the annotation, which is a price
worth paying for a number that cannot be misread.

### Two counts of the same thing

The roster annotates each member's monthly usage in SQL; the detail page computes it
with `free_admissions_in`. They must agree, including at month boundaries. The tests
cover both paths against the same fixture rather than trusting that two
implementations of "this calendar month" drifted the same way.

## Testing

`.venv/bin/python manage.py test`, `flake8`, as established.

- **Calendar-month boundaries.** A redemption on 31 August does not count against
  September; one on 1 September does. This is the decision most likely to be got
  subtly wrong, so it is tested at both edges rather than in the middle of a month.
- **Allowance resolves through the current term's tier**, and is 0 for a lapsed member
  even if their expired term's tier granted four.
- **Over-allowance is recorded, not rejected**, and is visible as such.
- **A tier granting 0 renders `—`**, not `0/0`, and offers no Redeem button.
- **The roster's query count does not change** with the number of members — pinned by
  extending the existing `assertNumQueries` test rather than adding a parallel one.
- **`recorded_by` survives** the deletion of the staff account that set it.
- **Deleting a redemption** removes only that row.

## Rollout

`manage.py migrate` and nothing else. No environment variables, no external
configuration, no public-site change — this is entirely behind staff login.

The allowance numbers ship in the migration and are editable in the admin afterwards,
so getting them wrong is a correction, not a deploy.

The local database is stale sqlite, not production; nothing here can be verified
against real membership data before deploy.
