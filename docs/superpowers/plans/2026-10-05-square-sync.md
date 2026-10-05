# Square Sync Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Every confirmed engagement gets a five-tier ticket item in Square, every Square sale line is pulled nightly into Django, and the two flash-gross emails are sent from Django to admin-managed recipients.

**Architecture:** A new `boxoffice` app owns the Square gateway, the link tables, the sales ledger, the email report settings, and two management commands. The push side is a pure `desired_item()` spec compared against stored link rows, called after dashboard transactions commit and again by a nightly reconcile. The pull side searches completed orders by Eastern business day, upserts `SaleLine` rows on a unique key, attributes lines by variation ID, and recomputes `Engagement.admissions`. Reports are aggregations over the ledger, so they can be re-run for any day without Square.

**Tech Stack:** Django 5.2.3, `squareup==42.1.0.20250521` (official SDK), Django's SMTP email backend, htmx + Alpine dashboard, `manage.py test` + `flake8`.

**Spec:** `docs/superpowers/specs/2026-10-05-square-sync-design.md`

## Global Constraints

- **The virtualenv is broken on this machine.** `.venv/pyvenv.cfg` points at `/usr/bin/python3.13`, which no longer exists (only 3.12.3 is installed), so `.venv/bin/python` fails. Before Task 1, rebuild it from the repo root: `python3 -m venv --clear .venv && .venv/bin/pip install -r requirements.txt -r dev-requirements.txt`. Every later command assumes `.venv/bin/python` works. Do not commit `.venv`.
- **Tests:** `.venv/bin/python manage.py test <label> -v 2`. Full suite: `.venv/bin/python manage.py test`. Django's test runner swaps in the locmem email backend; assert on `django.core.mail.outbox`.
- **Lint:** `.venv/bin/python -m flake8 <paths>`; `max-line-length = 88`, migrations excluded. `dashboard/views.py`, `dashboard/urls.py`, `dashboard/forms.py`, and `dashboard/tests/test_engagements.py` carry pre-existing flake8 debt. Lint only the paths each task names; never "fix" lines you did not write.
- **Import direction.** `boxoffice` imports `cinema` and `web.constants`. `cinema` never imports `boxoffice`. `dashboard` may import `boxoffice` (it already imports `cinema`, `audience`, `phone`).
- **Only `boxoffice/gateway.py` imports `square`.** Every other module takes a gateway object and tests pass `boxoffice.tests.fakes.FakeGateway`.
- **A blank `SQUARE_ACCESS_TOKEN` disables everything.** `get_gateway()` returns `None`; every entry point that receives `None` returns without error and without logging more than once at INFO.
- **Tiers come from `web.constants.TICKET_PRICES`.** The priced tiers are the keys whose value is an `int`, in dict order: `adult 8, senior 7, child 6, matinee 6, member 4`. `matinee_until` is a `datetime.time` and is never a tier. Variation names are the tier key title-cased: `Adult`, `Senior`, `Child`, `Matinee`, `Member`. Prices are pushed in cents.
- **Identifiers.** SKU `fkc-eng-<engagement_id>-<tier>`. Batch-upsert client IDs `#eng-<id>` and `#eng-<id>-<tier>`.
- **Business day** is the Eastern calendar day of the order's `closed_at`. `settings.TIME_ZONE` is already `America/New_York`; use `zoneinfo.ZoneInfo("America/New_York")` explicitly in `boxoffice/pull.py` so the rule does not depend on settings.
- **Spec amendment: no `ecom_visibility`.** SDK 42's `CatalogItemParams` has no `ecom_visibility` key. Omit it; items are register items by virtue of not being added to any Square Online channel.
- **Spec amendment: `SquareItem.engagement` is a `ForeignKey`, not a `OneToOneField`,** with a partial unique constraint "one row per engagement where `deleted_at` is null". A run that is re-confirmed after the reconcile deleted its item needs a fresh Square item while the old row stays for old sales. `related_name="square_items"`; `boxoffice.sync.live_item(engagement)` returns the one live row or `None`.
- **Migrations:** `boxoffice.0001_initial` (generated, Task 1), `boxoffice.0002_emailreport_emailrecipient` (generated, Task 2), `boxoffice.0003_seed_email_reports` (hand-written, Task 2), `cinema.0018_engagement_in_ticket_report` (generated, Task 3). Latest existing is `cinema.0017_vote_drop_email_preference`.
- **Spec amendment: `SquareItem.square_id` is nullable** (`null=True, blank=True`, still `unique=True`; NULLs do not collide). A first push that fails leaves a live row with no Square ID and a `last_error`, so the red pill and the Retry button work for a run that never made it into Square. `version` defaults to 0 for such a row.
- **Every dashboard view is staff-only** via `StaffRequiredMixin` from `dashboard/mixins.py`.
- **Commit after each task** with a conventional-commit subject (`feat(boxoffice): …`) and the attribution trailer the session provides.

## Review Focus

Inputs the spec implies but did not name. Each has a test in the task that owns the code.

1. **A line with no `catalog_object_id`** (a custom amount typed at the register) must be stored unattributed with a blank ID, not skipped or crash. → Task 8.
2. **An engagement whose `display_title` is empty** (no films, no event title) must not reach Square with an empty name; `desired_item` raises and `push` records the error. → Tasks 4 and 6.
3. **A run re-confirmed after its item was deleted** (status set back to Confirmed, end date extended) must get a new Square item while the old `SquareItem` row keeps its `deleted_at`. → Task 6.
4. **Deleting an engagement that never had an item** must succeed without calling Square, token or no token. → Tasks 6 and 11.
5. **A report whose only recipients are CC** has no `To` address; it is skipped and recorded as not sent rather than mailed with an empty To header. → Task 9.

---

### Task 1: The `boxoffice` app and its link and ledger tables

**Files:**
- Create: `boxoffice/__init__.py`, `boxoffice/apps.py`
- Create: `boxoffice/models/__init__.py`, `boxoffice/models/square_item.py`, `boxoffice/models/square_variation.py`, `boxoffice/models/sale_line.py`, `boxoffice/models/sales_pull.py`
- Create: `boxoffice/migrations/0001_initial.py` (generated)
- Create: `boxoffice/tests/__init__.py`, `boxoffice/tests/test_models.py`
- Modify: `fortkentcinema/settings.py:36-52` (add `"boxoffice.apps.BoxofficeConfig"` after `"phone.apps.PhoneConfig"`) and append the `SQUARE_*` settings after the Twilio block (`:245`)
- Modify: `requirements.txt` (append the Square SDK block)

**Interfaces:**
- Produces models exactly as the spec's Data model section, with these amendments: `SquareItem.square_id = CharField(max_length=64, unique=True, null=True, blank=True)`; `SquareItem.version = BigIntegerField(default=0)`; `SquareItem.engagement = ForeignKey(Engagement, null=True, on_delete=SET_NULL, related_name="square_items")`; `UniqueConstraint(fields=["engagement"], condition=Q(deleted_at__isnull=True), name="boxoffice_one_live_item_per_engagement")`; `SquareVariation` has `UniqueConstraint(fields=["item", "tier"], name="boxoffice_one_variation_per_tier")`; `SaleLine` has `UniqueConstraint(fields=["order_id", "line_uid"], name="boxoffice_one_row_per_order_line")`.
- `SalesPull.Status` is a `TextChoices` with `OK` and `FAILED`.
- Settings: `SQUARE_ACCESS_TOKEN`, `SQUARE_LOCATION_ID`, `SQUARE_TICKET_CATEGORY_ID` default `""`; `SQUARE_ENVIRONMENT` default `"sandbox"`.

- [ ] **Step 1: Rebuild the virtualenv** (see Global Constraints) and confirm `.venv/bin/python manage.py test cinema.tests.test_models -v 1` passes before touching anything.

- [ ] **Step 2: Add the dependency block to `requirements.txt`**

```
# Square (boxoffice app: ticket items pushed, sales pulled)
squareup==42.1.0.20250521
httpx==0.28.1
httpcore==1.0.9
h11==0.16.0
anyio==4.15.1
pydantic==2.13.5
pydantic_core==2.46.5
annotated-types==0.8.0
typing-inspection==0.4.4
```

`certifi`, `idna`, and `typing_extensions` are already pinned; squareup's floors are satisfied by the existing pins. Run `.venv/bin/pip install -r requirements.txt` and `.venv/bin/python -c "import square"`.

- [ ] **Step 3: Write the failing tests**

`boxoffice/tests/test_models.py`:

```python
import datetime

from boxoffice.models import SaleLine, SalesPull, SquareItem, SquareVariation
from cinema.models import Engagement, Screen
from django.db import IntegrityError, transaction
from django.test import TestCase
from django.utils import timezone


def make_eng(**over):
    screen = Screen.objects.get_or_create(name="Screen 1", capacity=50)[0]
    defaults = dict(screen=screen, start_date=datetime.date(2026, 10, 9),
                    end_date=datetime.date(2026, 10, 15), status="CONFIRMED")
    defaults.update(over)
    return Engagement.objects.create(**defaults)


class SquareItemTests(TestCase):
    def test_two_live_items_for_one_engagement_refused(self) -> None:
        eng = make_eng()
        SquareItem.objects.create(engagement=eng, square_id="A", version=1, name="X")
        with self.assertRaises(IntegrityError), transaction.atomic():
            SquareItem.objects.create(engagement=eng, square_id="B", version=1, name="X")

    def test_deleted_item_does_not_block_a_new_live_one(self) -> None:
        eng = make_eng()
        SquareItem.objects.create(engagement=eng, square_id="A", version=1, name="X",
                                  deleted_at=timezone.now())
        SquareItem.objects.create(engagement=eng, square_id="B", version=1, name="X")
        self.assertEqual(eng.square_items.count(), 2)

    def test_deleting_engagement_keeps_item_row(self) -> None:
        eng = make_eng()
        item = SquareItem.objects.create(engagement=eng, square_id="A", version=1, name="X")
        eng.delete()
        item.refresh_from_db()
        self.assertIsNone(item.engagement)


class SquareVariationTests(TestCase):
    def test_one_variation_per_tier(self) -> None:
        item = SquareItem.objects.create(engagement=make_eng(), square_id="A", version=1, name="X")
        SquareVariation.objects.create(item=item, square_id="V1", sku="fkc-eng-1-adult",
                                       tier="adult", name="Adult", price_cents=800, ordinal=0)
        with self.assertRaises(IntegrityError), transaction.atomic():
            SquareVariation.objects.create(item=item, square_id="V2", sku="fkc-eng-1-adult-2",
                                           tier="adult", name="Adult", price_cents=800, ordinal=1)


class SaleLineTests(TestCase):
    def test_order_line_is_unique(self) -> None:
        kwargs = dict(order_id="O1", line_uid="L1", business_date=datetime.date(2026, 10, 9),
                      closed_at=timezone.now(), item_name="Dune", quantity=1, gross_cents=800)
        SaleLine.objects.create(**kwargs)
        with self.assertRaises(IntegrityError), transaction.atomic():
            SaleLine.objects.create(**kwargs)


class SalesPullTests(TestCase):
    def test_status_choices(self) -> None:
        self.assertEqual(SalesPull.Status.OK, "OK")
        self.assertEqual(SalesPull.Status.FAILED, "FAILED")
```

- [ ] **Step 4: Run tests to verify they fail**

Run: `.venv/bin/python manage.py test boxoffice -v 2`
Expected: FAIL — `ModuleNotFoundError: No module named 'boxoffice'`.

- [ ] **Step 5: Create the app, models, settings, and migration**

`boxoffice/apps.py`: `BoxofficeConfig` with `default_auto_field = "django.db.models.BigAutoField"`, `name = "boxoffice"`, `verbose_name = "Box Office"`. Register it in `INSTALLED_APPS`.

Models one per file, re-exported from `boxoffice/models/__init__.py` with `__all__` like `phone/models/__init__.py`. Field types and defaults exactly as the spec's tables plus the amendments in Interfaces. `SaleLine.Meta.indexes` on `business_date` and `catalog_object_id` come from `db_index=True`. `SalesPull.Meta.ordering = ["-business_date", "-started_at"]`.

Settings block, after `TWILIO_WEBHOOK_BASE_URL`:

```python
# Square (boxoffice app). An empty token disables the sync: dashboard saves
# succeed as before and the nightly commands exit without calling out.
SQUARE_ACCESS_TOKEN = config("SQUARE_ACCESS_TOKEN", default="")
SQUARE_LOCATION_ID = config("SQUARE_LOCATION_ID", default="")
SQUARE_TICKET_CATEGORY_ID = config("SQUARE_TICKET_CATEGORY_ID", default="")
SQUARE_ENVIRONMENT = config("SQUARE_ENVIRONMENT", default="sandbox")
```

Run `.venv/bin/python manage.py makemigrations boxoffice` → `0001_initial.py`.

- [ ] **Step 6: Run tests to verify they pass**

Run: `.venv/bin/python manage.py test boxoffice -v 2`
Expected: 6 tests PASS. Then `.venv/bin/python -m flake8 boxoffice`.

- [ ] **Step 7: Commit**

```bash
git add boxoffice requirements.txt fortkentcinema/settings.py
git commit -m "feat(boxoffice): app, Square link tables, sales ledger, pull log"
```

---

### Task 2: Admin-managed email reports

**Files:**
- Create: `boxoffice/models/email_report.py` (both `EmailReport` and `EmailRecipient`; they change together)
- Modify: `boxoffice/models/__init__.py`
- Create: `boxoffice/admin.py`
- Create: `boxoffice/migrations/0002_emailreport_emailrecipient.py` (generated)
- Create: `boxoffice/migrations/0003_seed_email_reports.py` (hand-written)
- Create: `boxoffice/tests/test_email_report.py`

**Interfaces:**
- `EmailReport.Kind` TextChoices: `OWNER_SUMMARY = "OWNER_SUMMARY", "Owner summary"`, `TICKET_REPORT = "TICKET_REPORT", "Ticket report"`. Fields `kind` (unique), `subject`, `enabled`.
- `EmailRecipient(report FK related_name="recipients", address EmailField, cc BooleanField default False)`, `UniqueConstraint(report, address)`.
- `EmailReport.to_addresses() -> list[str]` and `EmailReport.cc_addresses() -> list[str]`.
- Seed: `OWNER_SUMMARY` subject `"Daily Sales Summary"`; `TICKET_REPORT` subject `"Ticket Sales Report"`. The owner edits the ticket subject in the admin at rollout.

- [ ] **Step 1: Write the failing tests**

```python
from boxoffice.models import EmailRecipient, EmailReport
from django.db import IntegrityError, transaction
from django.test import TestCase


class EmailReportSeedTests(TestCase):
    def test_both_reports_seeded(self) -> None:
        self.assertEqual(
            set(EmailReport.objects.values_list("kind", flat=True)),
            {"OWNER_SUMMARY", "TICKET_REPORT"},
        )
        self.assertEqual(EmailReport.objects.get(kind="OWNER_SUMMARY").subject,
                         "Daily Sales Summary")
        self.assertTrue(EmailReport.objects.get(kind="TICKET_REPORT").enabled)


class EmailRecipientTests(TestCase):
    def test_to_and_cc_split(self) -> None:
        report = EmailReport.objects.get(kind="OWNER_SUMMARY")
        EmailRecipient.objects.create(report=report, address="owner@example.com")
        EmailRecipient.objects.create(report=report, address="cc@example.com", cc=True)
        self.assertEqual(report.to_addresses(), ["owner@example.com"])
        self.assertEqual(report.cc_addresses(), ["cc@example.com"])

    def test_duplicate_address_per_report_refused(self) -> None:
        report = EmailReport.objects.get(kind="TICKET_REPORT")
        EmailRecipient.objects.create(report=report, address="a@example.com")
        with self.assertRaises(IntegrityError), transaction.atomic():
            EmailRecipient.objects.create(report=report, address="a@example.com", cc=True)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/python manage.py test boxoffice.tests.test_email_report -v 2`
Expected: FAIL — `ImportError: cannot import name 'EmailReport'`.

- [ ] **Step 3: Implement the models, admin, and seed**

Models per Interfaces. `makemigrations boxoffice` → `0002_emailreport_emailrecipient.py`. Hand-write `0003_seed_email_reports.py` in the style of `audience/migrations/0007_seed_free_admission_allowances.py`: `RunPython(seed, unseed)` where `seed` does `get_or_create(kind=..., defaults={"subject": ...})` for both kinds and `unseed` deletes both.

`boxoffice/admin.py`: `EmailRecipientInline(admin.TabularInline)` with `extra = 1`; `@admin.register(EmailReport)` with `list_display = ("kind", "subject", "enabled")`, `inlines = [EmailRecipientInline]`. Also register `SalesPull` read-only (`list_display = ("business_date", "status", "orders", "lines", "owner_email_sent", "report_email_sent")`, `readonly_fields` = all) so the log is visible without a dashboard page.

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/python manage.py test boxoffice -v 2` then `.venv/bin/python -m flake8 boxoffice`.
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add boxoffice
git commit -m "feat(boxoffice): admin-managed email reports and recipients"
```

---

### Task 3: `Engagement.in_ticket_report`

**Files:**
- Modify: `cinema/models/engagement.py:58-62` (add the field after `is_free_for_members`)
- Create: `cinema/migrations/0018_engagement_in_ticket_report.py` (generated)
- Modify: `cinema/admin.py:55` (`list_filter` gains `"in_ticket_report"`)
- Modify: `dashboard/forms.py:61-63` (`fields` gains `"in_ticket_report"` after `"is_free_for_members"`)
- Modify: `dashboard/templates/dashboard/_engagement_form.html:61-65` (Listing section)
- Test: `cinema/tests/test_models.py` (append), `dashboard/tests/test_engagements.py` (append)

**Interfaces:**
- Produces `Engagement.in_ticket_report: BooleanField(default=True)` with help text: `"Include this run's ticket sales in the nightly ticket report sent to the booker. Untick for runs that owe no distributor royalty, such as a Classic Movie Night; they still appear in the owner's summary."`

- [ ] **Step 1: Write the failing tests**

Append to `cinema/tests/test_models.py`:

```python
class InTicketReportTests(TestCase):
    def test_defaults_true(self) -> None:
        screen = Screen.objects.create(name="S", capacity=10)
        eng = Engagement.objects.create(screen=screen, start_date=datetime.date(2026, 10, 9),
                                        end_date=datetime.date(2026, 10, 9))
        self.assertTrue(eng.in_ticket_report)
```

Append to `EngagementCreateTests` in `dashboard/tests/test_engagements.py` (line 145), using its `_payload` helper:

```python
    def test_in_ticket_report_unticked_saves_false(self) -> None:
        payload = self._payload()
        payload.pop("in_ticket_report", None)  # an unticked checkbox is absent from POST
        self.client.post(reverse("dashboard:engagement_create"), payload)
        self.assertFalse(Engagement.objects.get().in_ticket_report)

    def test_in_ticket_report_ticked_saves_true(self) -> None:
        self.client.post(reverse("dashboard:engagement_create"),
                         self._payload(in_ticket_report="on"))
        self.assertTrue(Engagement.objects.get().in_ticket_report)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/python manage.py test cinema.tests.test_models dashboard.tests.test_engagements -v 2`
Expected: FAIL — `in_ticket_report` unknown attribute / unexpected keyword.

- [ ] **Step 3: Implement**

Field, migration, admin filter, form field, and in the template's Listing section add `{% field form.in_ticket_report label="Include in ticket report" %}` after the free-for-members line. Note the existing `_payload` helper omits `is_free_for_members`, and `show_in_main_listings` is `"on"`; follow that convention.

- [ ] **Step 4: Run tests to verify they pass**

Run the same label. Then `.venv/bin/python -m flake8 cinema/models/engagement.py cinema/admin.py cinema/tests/test_models.py`.

- [ ] **Step 5: Commit**

```bash
git add cinema dashboard/forms.py dashboard/templates/dashboard/_engagement_form.html dashboard/tests/test_engagements.py
git commit -m "feat(cinema): in_ticket_report flag on engagements"
```

---

### Task 4: The pure item spec

**Files:**
- Create: `boxoffice/spec.py`
- Create: `boxoffice/tests/test_spec.py`

**Interfaces:**
- Produces:

```python
@dataclass(frozen=True)
class VariationSpec:
    tier: str          # "adult" … "member"
    name: str          # "Adult" … "Member"
    sku: str           # "fkc-eng-<id>-<tier>"
    price_cents: int
    ordinal: int

@dataclass(frozen=True)
class ItemSpec:
    engagement_id: int
    name: str
    variations: tuple[VariationSpec, ...]

def priced_tiers() -> list[tuple[str, int]]      # [("adult", 8), …] from TICKET_PRICES
def desired_item(engagement: Engagement) -> ItemSpec   # raises ValueError on empty name
```

- [ ] **Step 1: Write the failing tests**

```python
import datetime

from boxoffice.spec import ItemSpec, desired_item, priced_tiers
from cinema.models import Engagement, EngagementFilm, Film, Screen
from django.test import TestCase


class PricedTiersTests(TestCase):
    def test_five_tiers_in_constant_order(self) -> None:
        self.assertEqual(priced_tiers(), [
            ("adult", 8), ("senior", 7), ("child", 6), ("matinee", 6), ("member", 4),
        ])


class DesiredItemTests(TestCase):
    def setUp(self) -> None:
        screen = Screen.objects.create(name="S1", capacity=50)
        self.eng = Engagement.objects.create(
            screen=screen, start_date=datetime.date(2026, 10, 9),
            end_date=datetime.date(2026, 10, 15), status="CONFIRMED")
        EngagementFilm.objects.create(engagement=self.eng,
                                      film=Film.objects.create(title="Dune"), position=1)

    def test_item_name_is_display_title(self) -> None:
        self.assertEqual(desired_item(self.eng).name, "Dune")

    def test_five_variations_with_prices_skus_ordinals(self) -> None:
        spec = desired_item(self.eng)
        self.assertIsInstance(spec, ItemSpec)
        self.assertEqual(
            [(v.tier, v.name, v.price_cents, v.ordinal) for v in spec.variations],
            [("adult", "Adult", 800, 0), ("senior", "Senior", 700, 1),
             ("child", "Child", 600, 2), ("matinee", "Matinee", 600, 3),
             ("member", "Member", 400, 4)],
        )
        self.assertEqual(spec.variations[3].sku, f"fkc-eng-{self.eng.pk}-matinee")

    def test_free_for_members_changes_nothing(self) -> None:
        self.eng.is_free_for_members = True
        self.assertEqual(desired_item(self.eng).variations[4].price_cents, 400)

    def test_empty_title_raises(self) -> None:
        self.eng.engagement_films.all().delete()
        with self.assertRaises(ValueError):
            desired_item(self.eng)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/python manage.py test boxoffice.tests.test_spec -v 2`
Expected: FAIL — `ModuleNotFoundError: boxoffice.spec`.

- [ ] **Step 3: Implement `boxoffice/spec.py`**

`priced_tiers()` filters `TICKET_PRICES.items()` to `isinstance(value, int)`. `desired_item` raises `ValueError("Engagement <id> has no title to send to Square")` when `display_title` is blank.

- [ ] **Step 4: Run tests to verify they pass**, then `flake8 boxoffice`.

- [ ] **Step 5: Commit**

```bash
git add boxoffice/spec.py boxoffice/tests/test_spec.py
git commit -m "feat(boxoffice): pure ticket item spec from TICKET_PRICES"
```

---

### Task 5: The Square gateway and its fake

**Files:**
- Create: `boxoffice/gateway.py`
- Create: `boxoffice/tests/fakes.py`
- Create: `boxoffice/tests/test_gateway.py`

**Interfaces:**
- Produces, in `boxoffice/gateway.py`:

```python
class GatewayError(Exception): ...
class VersionMismatch(GatewayError): ...

@dataclass(frozen=True)
class RemoteItem:
    item_id: str
    version: int
    name: str
    variation_ids_by_sku: dict[str, str]

@dataclass(frozen=True)
class UpsertResult:
    item_id: str
    version: int
    variation_ids_by_tier: dict[str, str]

@dataclass(frozen=True)
class OrderLine:
    uid: str
    name: str
    variation_name: str
    catalog_object_id: str     # "" when absent
    quantity: int
    gross_cents: int           # total_money.amount

@dataclass(frozen=True)
class OrderData:
    order_id: str
    closed_at: datetime.datetime   # aware
    lines: tuple[OrderLine, ...]

class SquareGateway:
    def __init__(self, client, location_id: str, category_id: str) -> None
    def upsert_item(self, spec: ItemSpec, *, item_id: str | None, version: int | None,
                    variation_ids_by_tier: dict[str, str]) -> UpsertResult
    def delete_item(self, item_id: str) -> None
    def retrieve_item(self, item_id: str) -> RemoteItem
    def search_orders(self, start: datetime.datetime, end: datetime.datetime) -> list[OrderData]
    def list_ticket_items(self) -> list[RemoteItem]          # items in category_id
    def lookup_categories(self, variation_ids: list[str]) -> dict[str, str]  # variation id -> category id

def get_gateway() -> SquareGateway | None   # None when settings.SQUARE_ACCESS_TOKEN is ""
```

- `boxoffice/tests/fakes.py` produces `FakeGateway` implementing the same methods over in-memory dicts: `items: dict[str, RemoteItem]`, `orders: list[OrderData]`, `categories: dict[str, str]`, `calls: list[tuple]` (method name + args, for "no call made" assertions), and `fail_with: GatewayError | None` (raised by every method when set). `upsert_item` mints IDs `item-<n>` / `var-<n>`, bumps version, and raises `VersionMismatch` when `version` is given and differs from the stored one. `delete_item` of an unknown id raises `GatewayError`.

SDK facts (verified against `squareup==42.1.0.20250521`):

- `square.Square(token=..., environment=SquareEnvironment.SANDBOX | PRODUCTION)`.
- `client.catalog.batch_upsert(idempotency_key=str(uuid4()), batches=[{"objects": [item_obj]}])` → `.id_mappings` (`client_object_id`, `object_id`) and `.objects[0].version`. The item object is `{"type": "ITEM", "id": "#eng-42" | square_id, "version": v (updates only), "present_at_all_locations": False, "present_at_location_ids": [loc], "item_data": {"name", "product_type": "REGULAR", "is_taxable": False, "categories": [{"id": cat}], "reporting_category": {"id": cat}, "variations": [{"type": "ITEM_VARIATION", "id": "#eng-42-adult" | var_id, "present_at_all_locations": False, "present_at_location_ids": [loc], "item_variation_data": {"item_id": <item id or temp>, "name", "sku", "ordinal", "pricing_type": "FIXED_PRICING", "price_money": {"amount": cents, "currency": "USD"}}}]}}`. Variations that already have a Square ID are sent with their ID and the item's `version` (Square versions all objects in an upsert together).
- `client.catalog.batch_delete(object_ids=[item_id])` deletes the item and its variations.
- `client.catalog.object.get(object_id, include_related_objects=True)` → `.object` (`.version`, `.item_data.name`, `.item_data.variations[*].id` and `.item_variation_data.sku`).
- `client.orders.search(location_ids=[loc], query={"filter": {"state_filter": {"states": ["COMPLETED"]}, "date_time_filter": {"closed_at": {"start_at": iso, "end_at": iso}}}, "sort": {"sort_field": "CLOSED_AT", "sort_order": "ASC"}}, cursor=...)` → `.orders`, `.cursor`; loop until cursor is falsy. Each order: `.id`, `.closed_at` (RFC 3339 string; parse with `datetime.datetime.fromisoformat`), `.line_items[*]` with `.uid`, `.name`, `.variation_name`, `.catalog_object_id`, `.quantity` (string like `"1.00000000"` → `int(float(q))`), `.total_money.amount`.
- `client.catalog.list(types="ITEM")` is a pager; iterate it. An item is a ticket item when `category_id` appears in `item.item_data.categories[*].id`.
- `client.catalog.batch_get(object_ids=variation_ids, include_related_objects=True)` → `.objects` (variations, each `.item_variation_data.item_id`) and `.related_objects` (items with `.item_data.categories`).
- Errors arrive as `square.core.api_error.ApiError` with `.status_code` and `.body`; `VERSION_MISMATCH` appears as `errors[*].code == "VERSION_MISMATCH"` in the body. Wrap every SDK call: translate `ApiError` to `VersionMismatch` when that code is present, else `GatewayError(str(body))`.

- [ ] **Step 1: Write the failing tests**

`test_gateway.py` uses `unittest.mock.Mock()` as the client and asserts on the request the gateway builds — the one place the SDK's vocabulary is checked.

```python
class UpsertRequestTests(SimpleTestCase):
    def test_create_builds_temp_ids_and_five_variations(self) -> None:
        client = mock.Mock()
        client.catalog.batch_upsert.return_value = mock.Mock(
            id_mappings=[mock.Mock(client_object_id="#eng-7", object_id="I1")]
            + [mock.Mock(client_object_id=f"#eng-7-{t}", object_id=f"V{i}")
               for i, t in enumerate(["adult", "senior", "child", "matinee", "member"])],
            objects=[mock.Mock(version=3)],
        )
        gw = SquareGateway(client, location_id="LOC", category_id="CAT")
        result = gw.upsert_item(SPEC_FOR_7, item_id=None, version=None, variation_ids_by_tier={})
        kwargs = client.catalog.batch_upsert.call_args.kwargs
        item = kwargs["batches"][0]["objects"][0]
        self.assertEqual(item["id"], "#eng-7")
        self.assertNotIn("version", item)
        self.assertEqual(item["item_data"]["categories"], [{"id": "CAT"}])
        self.assertEqual(item["item_data"]["reporting_category"], {"id": "CAT"})
        self.assertFalse(item["item_data"]["is_taxable"])
        self.assertEqual(item["present_at_location_ids"], ["LOC"])
        variations = item["item_data"]["variations"]
        self.assertEqual([v["id"] for v in variations],
                         [f"#eng-7-{t}" for t in ["adult", "senior", "child", "matinee", "member"]])
        self.assertEqual(variations[0]["item_variation_data"]["price_money"],
                         {"amount": 800, "currency": "USD"})
        self.assertEqual(variations[0]["item_variation_data"]["sku"], "fkc-eng-7-adult")
        self.assertEqual(result, UpsertResult("I1", 3, {"adult": "V0", "senior": "V1", "child": "V2",
                                                        "matinee": "V3", "member": "V4"}))

    def test_update_sends_stored_ids_and_version(self) -> None:
        ...  # item["id"] == "I1", item["version"] == 3, variation ids reused by tier

    def test_version_mismatch_is_typed(self) -> None:
        client = mock.Mock()
        client.catalog.batch_upsert.side_effect = ApiError(
            status_code=400, body={"errors": [{"code": "VERSION_MISMATCH", "detail": "x"}]})
        with self.assertRaises(VersionMismatch):
            SquareGateway(client, "LOC", "CAT").upsert_item(SPEC_FOR_7, item_id="I1", version=1,
                                                             variation_ids_by_tier={})


class SearchOrdersTests(SimpleTestCase):
    def test_filters_completed_by_closed_at_and_pages(self) -> None:
        ...  # two pages via cursor; asserts states == ["COMPLETED"], closed_at range, both orders returned

    def test_line_without_catalog_id_has_blank_id(self) -> None:
        ...  # line.catalog_object_id is None on the SDK object → "" on OrderLine

    def test_quantity_string_becomes_int(self) -> None:
        ...  # "2.00000000" → 2


class GetGatewayTests(SimpleTestCase):
    @override_settings(SQUARE_ACCESS_TOKEN="")
    def test_blank_token_returns_none(self) -> None:
        self.assertIsNone(get_gateway())

    @override_settings(SQUARE_ACCESS_TOKEN="tok", SQUARE_LOCATION_ID="L",
                       SQUARE_TICKET_CATEGORY_ID="C", SQUARE_ENVIRONMENT="sandbox")
    def test_token_builds_sandbox_gateway(self) -> None:
        with mock.patch("boxoffice.gateway.Square") as Square:
            gw = get_gateway()
        self.assertIsInstance(gw, SquareGateway)
        self.assertEqual(Square.call_args.kwargs["environment"], SquareEnvironment.SANDBOX)
```

`SPEC_FOR_7` is an `ItemSpec` built by hand in the test module (engagement 7, name "Dune"), not from the database; these are `SimpleTestCase`s.

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/python manage.py test boxoffice.tests.test_gateway -v 2`
Expected: FAIL — module not found.

- [ ] **Step 3: Implement `boxoffice/gateway.py` and `boxoffice/tests/fakes.py`**

Per Interfaces and the SDK facts. `get_gateway()` reads settings each call (so `override_settings` works) and maps `"production"` to `SquareEnvironment.PRODUCTION`, anything else to `SANDBOX`.

- [ ] **Step 4: Run tests to verify they pass**, then `flake8 boxoffice`.

- [ ] **Step 5: Commit**

```bash
git add boxoffice/gateway.py boxoffice/tests/fakes.py boxoffice/tests/test_gateway.py
git commit -m "feat(boxoffice): Square gateway over the official SDK, plus a fake for tests"
```

---

### Task 6: Push, delete, and schedule

**Files:**
- Create: `boxoffice/sync.py`
- Create: `boxoffice/tests/test_sync.py`

**Interfaces:**
- Consumes `desired_item`, `SquareGateway`/`FakeGateway`, `get_gateway`, the models.
- Produces:

```python
def live_item(engagement: Engagement) -> SquareItem | None
def should_have_item(engagement: Engagement, today: datetime.date) -> bool
    # CONFIRMED and end_date >= today
def push(engagement: Engagement, gateway: SquareGateway | None = None) -> SquareItem | None
    # gateway defaults to get_gateway(); None → return None without touching the db
def delete(engagement: Engagement, gateway: SquareGateway | None = None) -> None
    # no live item → return; live item with no square_id, or gateway None → set deleted_at locally
    # and return; otherwise delete_item then set deleted_at; raises GatewayError when Square refuses
def sync(engagement: Engagement, gateway: SquareGateway | None = None) -> None
    # push if should_have_item(engagement, localdate()) else delete; swallows and logs GatewayError
def schedule(engagement: Engagement) -> None
    # transaction.on_commit(lambda: sync(engagement))
```

`push` behaviour: build `spec = desired_item(engagement)`; on `ValueError` get-or-create the live row (no `square_id`), write the message to `last_error`, and return it. Compare against the live item's stored `name` and its variations' `(tier, name, sku, price_cents, ordinal)`; if equal and `last_error` is blank, return the item with no gateway call. Otherwise upsert with the stored `square_id`/`version`/variation IDs (or none for a fresh item), write back IDs and version, `synced_at=now`, `last_error=""`. On `VersionMismatch`: `retrieve_item`, re-upsert with the remote version and the remote `variation_ids_by_sku` mapped to tiers, once; log that an external edit was overwritten. On `GatewayError`: get-or-create the live row and set `last_error=str(exc)`; a row with no `square_id` is "never reached Square" and is retried by the pill's button and by the reconcile. Record the engagement's `display_title` in `name`.

- [ ] **Step 1: Write the failing tests**

Helpers at module top: `make_eng(**over)` as in Task 1 plus a film; `gw = FakeGateway()`.

```python
class PushTests(TestCase):
    def test_first_push_creates_item_and_five_variations(self) -> None:
        item = push(self.eng, gw)
        self.assertEqual(item.square_id, "item-1")
        self.assertEqual(item.variations.count(), 5)
        self.assertEqual(item.variations.get(tier="member").price_cents, 400)
        self.assertIsNotNone(item.synced_at)

    def test_unchanged_second_push_makes_no_call(self) -> None:
        push(self.eng, gw); gw.calls.clear()
        push(self.eng, gw)
        self.assertEqual(gw.calls, [])

    def test_rename_repushes_with_stored_version(self) -> None:
        item = push(self.eng, gw)
        self.eng.event_title = "Dune: Part One"; self.eng.save()
        push(self.eng, gw)
        self.assertEqual(gw.items[item.square_id].name, "Dune: Part One")
        self.assertEqual(gw.calls[-1][0], "upsert_item")
        self.assertEqual(gw.calls[-1][1]["version"], item.version)

    def test_version_mismatch_refetches_and_wins(self) -> None:
        item = push(self.eng, gw)
        gw.items[item.square_id] = dataclasses.replace(gw.items[item.square_id], version=99, name="Varity")
        self.eng.event_title = "Dune"; self.eng.save()
        push(self.eng, gw)
        self.assertEqual(gw.items[item.square_id].name, "Dune")
        item.refresh_from_db(); self.assertEqual(item.version, 100)

    def test_gateway_failure_records_error_and_keeps_engagement(self) -> None:
        item = push(self.eng, gw)
        gw.fail_with = GatewayError("boom")
        self.eng.event_title = "X"; self.eng.save()
        push(self.eng, gw)
        item.refresh_from_db(); self.assertEqual(item.last_error, "boom")
        self.assertTrue(Engagement.objects.filter(pk=self.eng.pk).exists())

    def test_empty_title_records_error_without_calling_square(self) -> None:
        self.eng.engagement_films.all().delete()
        item = push(self.eng, gw)
        self.assertIn("no title", item.last_error)
        self.assertIsNone(item.square_id)
        self.assertEqual(gw.calls, [])

    def test_first_push_failure_leaves_row_with_error_and_no_id(self) -> None:
        gw.fail_with = GatewayError("boom")
        item = push(self.eng, gw)
        self.assertEqual((item.square_id, item.last_error), (None, "boom"))
        gw.fail_with = None
        item = push(self.eng, gw)
        self.assertEqual((item.square_id, item.last_error), ("item-1", ""))

    def test_none_gateway_does_nothing(self) -> None:
        self.assertIsNone(push(self.eng, None))
        self.assertEqual(SquareItem.objects.count(), 0)

    def test_reconfirmed_run_after_deletion_gets_new_item(self) -> None:
        old = push(self.eng, gw)
        delete(self.eng, gw)
        new = push(self.eng, gw)
        self.assertNotEqual(old.pk, new.pk)
        old.refresh_from_db(); self.assertIsNotNone(old.deleted_at)
        self.assertEqual(live_item(self.eng).pk, new.pk)


class DeleteTests(TestCase):
    def test_delete_marks_row_and_removes_remote(self) -> None: ...
    def test_delete_without_item_is_noop(self) -> None:
        delete(self.eng, gw); self.assertEqual(gw.calls, [])
    def test_delete_failure_raises(self) -> None:
        push(self.eng, gw); gw.fail_with = GatewayError("nope")
        with self.assertRaises(GatewayError): delete(self.eng, gw)


class SyncAndScheduleTests(TestCase):
    def test_sync_pushes_confirmed_and_deletes_cancelled(self) -> None: ...
    def test_schedule_runs_after_commit(self) -> None:
        with mock.patch("boxoffice.sync.get_gateway", return_value=gw):
            with transaction.atomic():
                schedule(self.eng)
                self.assertEqual(SquareItem.objects.count(), 0)
            # TestCase wraps tests in a transaction; use self.captureOnCommitCallbacks(execute=True)
```

Use `self.captureOnCommitCallbacks(execute=True)` around the `schedule` call for the last test.

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/python manage.py test boxoffice.tests.test_sync -v 2`

- [ ] **Step 3: Implement `boxoffice/sync.py`** per Interfaces.

- [ ] **Step 4: Run tests to verify they pass**, then `flake8 boxoffice`.

- [ ] **Step 5: Commit**

```bash
git add boxoffice/sync.py boxoffice/tests/test_sync.py
git commit -m "feat(boxoffice): push, delete, and post-commit scheduling of ticket items"
```

---

### Task 7: Nightly reconcile and `sync_square_catalog`

**Files:**
- Modify: `boxoffice/sync.py` (append `reconcile`)
- Create: `boxoffice/management/__init__.py`, `boxoffice/management/commands/__init__.py`, `boxoffice/management/commands/sync_square_catalog.py`
- Test: `boxoffice/tests/test_sync.py` (append), `boxoffice/tests/test_commands.py` (create)

**Interfaces:**
- Produces:

```python
@dataclass
class ReconcileReport:
    pushed: list[int] = field(default_factory=list)     # engagement ids upserted
    deleted: list[int] = field(default_factory=list)
    unknown_items: list[str] = field(default_factory=list)  # "<name> (<id>)" in the ticket category, not Django's
    errors: list[str] = field(default_factory=list)

def reconcile(today: datetime.date, gateway: SquareGateway | None = None,
              *, dry_run: bool = False) -> ReconcileReport
```

With `dry_run=True` the report lists what would change and no gateway write or db write happens. "Unknown" means an item from `list_ticket_items()` whose `item_id` is not a live `SquareItem.square_id` and none of whose SKUs start with `fkc-eng-`. An item with `fkc-eng-` SKUs but no live row is reported separately in `errors` as `"Django-made item without a link row: <id>"` and left alone.

The command: `sync_square_catalog [--dry-run]`, prints one line per list in the report, exits 0 when `errors` is empty and 1 otherwise. With no gateway it prints `"Square sync disabled (no SQUARE_ACCESS_TOKEN)"` and exits 0.

- [ ] **Step 1: Write the failing tests**

Append to `test_sync.py`:

```python
class ReconcileTests(TestCase):
    def test_pushes_confirmed_future_and_deletes_ended(self) -> None:
        live = make_eng(end_date=datetime.date(2026, 10, 20))
        ended = make_eng(end_date=datetime.date(2026, 10, 1)); push(ended, gw)
        cancelled = make_eng(); push(cancelled, gw)
        Engagement.objects.filter(pk=cancelled.pk).update(status="CANCELLED")
        report = reconcile(datetime.date(2026, 10, 9), gw)
        self.assertEqual(report.pushed, [live.pk])
        self.assertEqual(sorted(report.deleted), sorted([ended.pk, cancelled.pk]))
        self.assertIsNone(live_item(ended))
        self.assertIsNone(live_item(cancelled))

    def test_repushes_item_edited_in_admin(self) -> None:
        eng = make_eng(); push(eng, gw)
        Engagement.objects.filter(pk=eng.pk).update(event_title="Renamed")
        report = reconcile(datetime.date(2026, 10, 9), gw)
        self.assertEqual(report.pushed, [eng.pk])
        self.assertEqual(gw.items[live_item(eng).square_id].name, "Renamed")

    def test_unknown_items_reported_not_deleted(self) -> None:
        gw.items["hand"] = RemoteItem("hand", 1, "Varity", {})
        report = reconcile(datetime.date(2026, 10, 9), gw)
        self.assertEqual(report.unknown_items, ["Varity (hand)"])
        self.assertIn("hand", gw.items)

    def test_dry_run_changes_nothing(self) -> None:
        eng = make_eng()
        report = reconcile(datetime.date(2026, 10, 9), gw, dry_run=True)
        self.assertEqual(report.pushed, [eng.pk])
        self.assertEqual(gw.calls, [c for c in gw.calls if c[0] == "list_ticket_items"])
        self.assertEqual(SquareItem.objects.count(), 0)
```

`test_commands.py`:

```python
class SyncSquareCatalogCommandTests(TestCase):
    def test_disabled_without_token(self) -> None:
        out = StringIO()
        with override_settings(SQUARE_ACCESS_TOKEN=""):
            call_command("sync_square_catalog", stdout=out)
        self.assertIn("disabled", out.getvalue())

    def test_dry_run_prints_plan(self) -> None:
        make_eng()
        out = StringIO()
        with mock.patch("boxoffice.management.commands.sync_square_catalog.get_gateway",
                        return_value=FakeGateway()):
            call_command("sync_square_catalog", "--dry-run", stdout=out)
        self.assertIn("Would push 1", out.getvalue())
```

- [ ] **Step 2: Run tests to verify they fail**
- [ ] **Step 3: Implement `reconcile` and the command.** Print format: `"Pushed N"` / `"Would push N"`, `"Deleted N"` / `"Would delete N"`, `"Unknown items in ticket category: …"`, one `"ERROR: …"` per error.
- [ ] **Step 4: Run tests to verify they pass**, then `flake8 boxoffice`.
- [ ] **Step 5: Commit**

```bash
git add boxoffice
git commit -m "feat(boxoffice): nightly catalog reconcile command"
```

---

### Task 8: The sales pull

**Files:**
- Create: `boxoffice/pull.py`
- Create: `boxoffice/tests/test_pull.py`

**Interfaces:**
- Consumes `OrderData`/`OrderLine`, `SquareGateway.search_orders`, `lookup_categories`, the models.
- Produces:

```python
EASTERN = ZoneInfo("America/New_York")

def day_bounds(day: datetime.date) -> tuple[datetime.datetime, datetime.datetime]
    # [midnight, next midnight) Eastern, aware
def business_date(closed_at: datetime.datetime) -> datetime.date
def pull_day(day: datetime.date, gateway: SquareGateway) -> SalesPull
    # one SalesPull row per call; status OK with counts, or FAILED with error text
def recompute_admissions(engagement_ids: Iterable[int]) -> None
```

`pull_day`: `search_orders(*day_bounds(day))`; for each line `update_or_create(order_id, line_uid, defaults=…)` with `business_date=business_date(order.closed_at)`, `variation = SquareVariation.objects.filter(square_id=line.catalog_object_id).first()` when the id is non-blank, `engagement = variation.item.engagement if variation else None`; `category_id` from `lookup_categories(unknown non-blank ids)` for lines with no variation (attributed lines get `settings.SQUARE_TICKET_CATEGORY_ID`). Then `recompute_admissions` for every engagement touched: `admissions = Sum(quantity)` over its `SaleLine`s, all time. Wrap in `transaction.atomic()`; a `GatewayError` writes a `FAILED` row and re-raises nothing (the command decides the exit code from the row).

- [ ] **Step 1: Write the failing tests**

```python
def order(order_id, closed_at, *lines) -> OrderData: ...
def line(uid, name, variation_name="", catalog_object_id="", quantity=1, gross_cents=800) -> OrderLine: ...

class BusinessDateTests(SimpleTestCase):
    def test_eastern_calendar_day(self) -> None:
        # 03:30 UTC on Oct 10 is 23:30 Eastern on Oct 9
        self.assertEqual(business_date(datetime.datetime(2026, 10, 10, 3, 30, tzinfo=datetime.UTC)),
                         datetime.date(2026, 10, 9))

    def test_day_bounds_are_eastern_midnights(self) -> None:
        start, end = day_bounds(datetime.date(2026, 10, 9))
        self.assertEqual(start.isoformat(), "2026-10-09T00:00:00-04:00")
        self.assertEqual(end.isoformat(), "2026-10-10T00:00:00-04:00")


class PullDayTests(TestCase):
    def setUp(self):  # engagement, pushed to FakeGateway so variation ids exist
        ...
        self.adult_id = live_item(self.eng).variations.get(tier="adult").square_id

    def test_lines_stored_and_attributed(self) -> None:
        gw.orders = [order("O1", at_eastern(2026, 10, 9, 19, 5),
                           line("L1", "Dune", "Adult", self.adult_id, 2, 1600),
                           line("L2", "Popcorn", "", "VPOP", 1, 500))]
        pull = pull_day(datetime.date(2026, 10, 9), gw)
        self.assertEqual((pull.status, pull.orders, pull.lines), ("OK", 1, 2))
        ticket = SaleLine.objects.get(line_uid="L1")
        self.assertEqual((ticket.engagement_id, ticket.quantity, ticket.gross_cents), (self.eng.pk, 2, 1600))
        self.assertIsNone(SaleLine.objects.get(line_uid="L2").engagement)

    def test_second_pull_changes_nothing(self) -> None: ...  # same rows, same count
    def test_line_without_catalog_id_is_kept_unattributed(self) -> None: ...  # catalog_object_id == ""
    def test_admissions_recomputed_for_linked_only(self) -> None:
        unlinked = make_eng(admissions=42)
        ...; pull_day(...)
        self.eng.refresh_from_db(); self.assertEqual(self.eng.admissions, 2)
        unlinked.refresh_from_db(); self.assertEqual(unlinked.admissions, 42)
    def test_gateway_failure_writes_failed_row(self) -> None:
        gw.fail_with = GatewayError("down")
        pull = pull_day(datetime.date(2026, 10, 9), gw)
        self.assertEqual((pull.status, pull.error), ("FAILED", "down"))
    def test_quiet_day_is_ok_with_zero_counts(self) -> None: ...
```

- [ ] **Step 2: Run tests to verify they fail**
- [ ] **Step 3: Implement `boxoffice/pull.py`** per Interfaces.
- [ ] **Step 4: Run tests to verify they pass**, then `flake8 boxoffice`.
- [ ] **Step 5: Commit**

```bash
git add boxoffice/pull.py boxoffice/tests/test_pull.py
git commit -m "feat(boxoffice): nightly sales pull into the ledger with attribution"
```

---

### Task 9: Reports and email

**Files:**
- Create: `boxoffice/reports.py`
- Create: `boxoffice/templates/boxoffice/email/owner_summary.txt`, `boxoffice/templates/boxoffice/email/ticket_report.txt`
- Modify: `fortkentcinema/settings.py` (append the `EMAIL_*` block after the Square block)
- Create: `boxoffice/tests/test_reports.py`

**Interfaces:**
- Produces:

```python
@dataclass(frozen=True)
class ItemTotal:
    name: str
    quantity: int
    gross_cents: int

def owner_summary(day: datetime.date) -> list[ItemTotal]
    # every SaleLine for the day grouped by item_name; sorted by gross desc, then name
def ticket_report(day: datetime.date) -> list[ItemTotal]
    # lines where (engagement is set and engagement.in_ticket_report) or
    # (engagement is null and category_id == settings.SQUARE_TICKET_CATEGORY_ID); grouped and sorted the same way
def tier_totals(day: datetime.date) -> dict[str, int]
    # {"adult": n, …} over attributed lines, every priced tier present (0 when none)
def render_report(kind: str, day: datetime.date, rows: list[ItemTotal]) -> str
def send_reports(day: datetime.date, pull: SalesPull, *, dry_run: bool = False) -> None
    # for each EmailReport: skip if not enabled, or no To address; else EmailMessage(subject, body,
    # to=to_addresses(), cc=cc_addresses()).send(); set pull.owner_email_sent / report_email_sent; pull.save()
```

Settings:

```python
# Nightly flash-gross emails (boxoffice app). Who receives them lives in the
# database (admin → Box Office → Email reports); how they are sent lives here.
EMAIL_BACKEND = (
    "django.core.mail.backends.console.EmailBackend"
    if DEBUG
    else "django.core.mail.backends.smtp.EmailBackend"
)
EMAIL_HOST = config("EMAIL_HOST", default="")
EMAIL_PORT = config("EMAIL_PORT", default=587, cast=int)
EMAIL_HOST_USER = config("EMAIL_HOST_USER", default="")
EMAIL_HOST_PASSWORD = config("EMAIL_HOST_PASSWORD", default="")
EMAIL_USE_TLS = config("EMAIL_USE_TLS", default=True, cast=bool)
DEFAULT_FROM_EMAIL = config("DEFAULT_FROM_EMAIL", default="webmaster@localhost")
```

Templates port the script's wording. `owner_summary.txt`:

```
Item Sales Summary:

{% for r in rows %}{{ r.name }}: {{ r.quantity }} sold for ${{ r.gross_dollars }}
{% empty %}No sales were recorded for {{ day|date:"F j, Y" }}.
{% endfor %}
Total: {{ total_quantity }} sold for ${{ total_dollars }}
```

`ticket_report.txt`:

```
🎟 Ticket Sales Summary:

{% for r in rows %}{{ r.name }}: {{ r.quantity }} sold, ${{ r.gross_dollars }} revenue
{% empty %}No ticket sales were recorded for {{ day|date:"F j, Y" }}.
{% endfor %}
Report generated for {{ day|date:"F j, Y" }}
```

`gross_dollars` is a property on `ItemTotal` returning `f"{self.gross_cents / 100:.2f}"`; `total_dollars` likewise in the context.

- [ ] **Step 1: Write the failing tests**

```python
class AggregationTests(TestCase):
    def test_owner_summary_groups_every_line(self) -> None: ...   # tickets + popcorn, sorted by gross desc
    def test_ticket_report_excludes_flagged_run_and_concessions(self) -> None:
        # eng A in_ticket_report=True, eng B False, popcorn unattributed with other category
        ...
        self.assertEqual([r.name for r in ticket_report(day)], ["A"])
    def test_ticket_report_includes_unattributed_ticket_category_lines(self) -> None: ...  # hand-made pre-cutover item
    def test_tier_totals_cover_all_five(self) -> None:
        self.assertEqual(tier_totals(day), {"adult": 2, "senior": 0, "child": 0, "matinee": 1, "member": 0})


class RenderTests(TestCase):
    def test_owner_summary_body_matches_script_shape(self) -> None:
        body = render_report("OWNER_SUMMARY", day, [ItemTotal("Dune", 2, 1600)])
        self.assertIn("Dune: 2 sold for $16.00", body)
        self.assertIn("Total: 2 sold for $16.00", body)
    def test_quiet_day_bodies(self) -> None:
        self.assertIn("No sales were recorded for October 9, 2026", render_report("OWNER_SUMMARY", day, []))
        self.assertIn("No ticket sales were recorded for October 9, 2026", render_report("TICKET_REPORT", day, []))


class SendReportsTests(TestCase):
    def setUp(self):  # recipients: owner To + cc; ticket To; a SalesPull row
    def test_sends_both_and_records(self) -> None:
        send_reports(day, self.pull)
        self.assertEqual(len(mail.outbox), 2)
        self.assertEqual(mail.outbox[0].cc, ["cc@example.com"])
        self.pull.refresh_from_db()
        self.assertTrue(self.pull.owner_email_sent and self.pull.report_email_sent)
    def test_disabled_report_skipped(self) -> None: ...
    def test_report_with_only_cc_is_skipped(self) -> None:
        EmailRecipient.objects.filter(report__kind="TICKET_REPORT").update(cc=True)
        send_reports(day, self.pull)
        self.assertEqual([m.subject for m in mail.outbox], ["Daily Sales Summary"])
        self.pull.refresh_from_db(); self.assertFalse(self.pull.report_email_sent)
    def test_dry_run_sends_nothing(self) -> None: ...
    def test_subject_comes_from_admin_row(self) -> None: ...
```

- [ ] **Step 2: Run tests to verify they fail**
- [ ] **Step 3: Implement** `boxoffice/reports.py`, the templates, and the settings block.
- [ ] **Step 4: Run tests to verify they pass**, then `flake8 boxoffice fortkentcinema/settings.py`.
- [ ] **Step 5: Commit**

```bash
git add boxoffice fortkentcinema/settings.py
git commit -m "feat(boxoffice): owner summary and ticket report emails from the ledger"
```

---

### Task 10: `pull_square_sales`

**Files:**
- Create: `boxoffice/management/commands/pull_square_sales.py`
- Test: `boxoffice/tests/test_commands.py` (append)

**Interfaces:**
- Consumes `pull_day`, `send_reports`, `get_gateway`, `EASTERN`.
- Command: `pull_square_sales [--date YYYY-MM-DD] [--days N] [--dry-run] [--no-email]`. Default date is today in Eastern; default `--days 3`. Pulls dates `target - (days-1) … target` oldest first, then `send_reports(target, pull_for_target)` unless `--no-email`. `--dry-run`: for each day call `gateway.search_orders(*day_bounds(day))` and print `"Would store N lines from M orders for <date>"`, skipping `pull_day`; then print both report bodies rendered from whatever the ledger already holds for the target date; write no rows, send no mail. Exit 1 (raise `CommandError`) if any pull's status is `FAILED`. No gateway → print the disabled line, exit 0.

- [ ] **Step 1: Write the failing tests**

```python
class PullSquareSalesCommandTests(TestCase):
    def test_pulls_three_days_and_emails_target_only(self) -> None:
        gw = FakeGateway(); ...  # orders on Oct 7 and Oct 9
        with mock.patch("boxoffice.management.commands.pull_square_sales.get_gateway", return_value=gw):
            call_command("pull_square_sales", "--date", "2026-10-09", stdout=StringIO())
        self.assertEqual(set(SalesPull.objects.values_list("business_date", flat=True)),
                         {datetime.date(2026, 10, 7), datetime.date(2026, 10, 8), datetime.date(2026, 10, 9)})
        self.assertEqual(len(mail.outbox), 2)
        self.assertIn("October 9, 2026", mail.outbox[1].body)

    def test_no_email_flag(self) -> None: ...
    def test_dry_run_writes_nothing(self) -> None:
        ...; self.assertEqual(SaleLine.objects.count(), 0); self.assertEqual(mail.outbox, [])
    def test_failed_pull_exits_nonzero(self) -> None:
        gw = FakeGateway(fail_with=GatewayError("down"))
        with self.assertRaises(CommandError): ...
    def test_disabled_without_token(self) -> None: ...
```

- [ ] **Step 2: Run tests to verify they fail**
- [ ] **Step 3: Implement the command.**
- [ ] **Step 4: Run tests to verify they pass**, then `flake8 boxoffice`.
- [ ] **Step 5: Commit**

```bash
git add boxoffice
git commit -m "feat(boxoffice): pull_square_sales command with three-day lookback and reports"
```

---

### Task 11: Dashboard hooks, the Square pill, and Retry

**Files:**
- Modify: `dashboard/views.py:369-446` (`EngagementCreateView.post`, `EngagementEditView.post`, `EngagementStatusView.post`, `EngagementDeleteView.post`), `:291-317` (`EngagementDetailView.get_context_data`), and add `EngagementSquareRetryView` after `EngagementDeleteView`
- Modify: `dashboard/urls.py:31` (add `path("engagements/<int:pk>/square/retry", views.EngagementSquareRetryView.as_view(), name="engagement_square_retry")`)
- Create: `dashboard/templates/dashboard/_square_pill.html`
- Modify: `dashboard/templates/dashboard/engagement_detail.html:44-45` (add an `infoRow` labelled `Square:` including the pill, after the Status row)
- Create: `dashboard/tests/test_square_views.py`

**Interfaces:**
- Consumes `boxoffice.sync.schedule`, `boxoffice.sync.delete`, `boxoffice.sync.push`, `boxoffice.sync.live_item`, `boxoffice.gateway.GatewayError`.
- Views:
  - Create/Edit: call `schedule(engagement)` inside the existing `with transaction.atomic():` block, after `save_engagement_films`.
  - Status: wrap the save in `with transaction.atomic():` and call `schedule(engagement)` inside it.
  - Delete: `try: delete(engagement) except GatewayError as exc: return _engagement_list_response(request, tab, toast={"kind": "error", "message": f"Square refused to delete the ticket item ({exc}). The engagement was kept."})` before `engagement.delete()`.
  - `EngagementSquareRetryView.post(request, pk)`: `push(engagement)` then `redirect("dashboard:engagement_detail", pk=pk)`.
  - Detail context adds `square_enabled = bool(settings.SQUARE_ACCESS_TOKEN)` and `square_item = live_item(engagement)`.
- Pill template, reusing `.status-badge` variants already in the design system:
  - not enabled → render nothing;
  - no live item → `<span class="status-badge status-draft">Not in Square</span>`;
  - `last_error` → `<span class="status-badge status-cancelled">Square sync failed</span> <span class="fieldHint">{{ square_item.last_error }}</span>` and a `<form method="post" action="{% url 'dashboard:engagement_square_retry' engagement.pk %}">{% csrf_token %}<button class="btn btn-secondary btn-sm">Retry</button></form>`;
  - else → `<span class="status-badge status-active">In Square · {{ square_item.variations.count }} variations · synced {{ square_item.synced_at|timesince }} ago</span>`.

- [ ] **Step 1: Write the failing tests**

```python
@override_settings(SQUARE_ACCESS_TOKEN="tok")
class EngagementSquareHookTests(TestCase):
    # setUp: staff login, screen, film, _payload like test_engagements

    def test_create_schedules_sync(self) -> None:
        with mock.patch("dashboard.views.schedule") as schedule:
            self.client.post(reverse("dashboard:engagement_create"), self._payload(status="CONFIRMED"))
        schedule.assert_called_once()

    def test_edit_and_status_schedule_sync(self) -> None: ...  # two calls across the two views

    def test_showtime_create_does_not_schedule(self) -> None: ...  # post to showtime_create; schedule not called

    def test_delete_refused_when_square_refuses(self) -> None:
        eng = make_eng(...)
        with mock.patch("dashboard.views.delete", side_effect=GatewayError("nope")):
            resp = self.client.post(reverse("dashboard:engagement_delete", args=[eng.pk]) + "?tab=CURRENT")
        self.assertTrue(Engagement.objects.filter(pk=eng.pk).exists())
        self.assertIn("The engagement was kept", resp.content.decode())

    def test_delete_without_item_proceeds(self) -> None:
        eng = make_eng(...)  # no SquareItem row, so delete() returns before touching a gateway
        self.client.post(reverse("dashboard:engagement_delete", args=[eng.pk]) + "?tab=CURRENT")
        self.assertFalse(Engagement.objects.filter(pk=eng.pk).exists())


@override_settings(SQUARE_ACCESS_TOKEN="tok")
class SquarePillTests(TestCase):
    def test_not_in_square(self) -> None: ...  # "Not in Square"
    def test_in_square(self) -> None:          # SquareItem + 5 variations → "In Square · 5 variations"
    def test_failed_with_retry(self) -> None:  # last_error → "Square sync failed", "Retry", the error text
    @override_settings(SQUARE_ACCESS_TOKEN="")
    def test_hidden_when_disabled(self) -> None: ...  # none of the three strings present


class RetryViewTests(TestCase):
    def test_requires_staff(self) -> None: ...  # 302 when logged out
    def test_calls_push_and_redirects(self) -> None:
        with mock.patch("dashboard.views.push") as push:
            resp = self.client.post(reverse("dashboard:engagement_square_retry", args=[eng.pk]))
        push.assert_called_once(); self.assertEqual(resp.status_code, 302)
```

Mock `dashboard.views.schedule` / `delete` / `push` because the view module imports them by name: `from boxoffice.sync import delete, live_item, push, schedule` and `from boxoffice.gateway import GatewayError`.

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/python manage.py test dashboard.tests.test_square_views -v 2`

- [ ] **Step 3: Implement** the view changes, URL, pill template, and detail row.

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/python manage.py test dashboard -v 1` (the whole dashboard suite; the engagement tests must still pass). Lint `dashboard/tests/test_square_views.py` and `dashboard/templates` are not linted; do not lint `dashboard/views.py` or `dashboard/urls.py` (pre-existing debt).

- [ ] **Step 5: Commit**

```bash
git add dashboard
git commit -m "feat(dashboard): sync engagements to Square on save; Square pill and Retry"
```

---

### Task 12: Home sales panel and smart alerts

**Files:**
- Modify: `boxoffice/reports.py` (append `sales_panel`, `pull_status`)
- Modify: `dashboard/smart_alerts.py:6-10` (two new keyword parameters) and append two alert blocks
- Modify: `dashboard/views.py:48-100` (`HomeView.get_context_data`)
- Modify: `dashboard/templates/dashboard/home.html:15-30` (a fourth `summaryGrid` card block, rendered only when `sales_panel` is not `None`)
- Test: `boxoffice/tests/test_reports.py` (append), `dashboard/tests/test_smart_alerts.py` (append), `dashboard/tests/test_home.py` (append)

**Interfaces:**
- Produces in `boxoffice/reports.py`:

```python
@dataclass(frozen=True)
class DaySales:
    gross_cents: int
    tickets: int            # Sum(quantity) over lines with engagement set
    concessions_cents: int  # Sum(gross_cents) over lines with engagement null

def day_sales(day: datetime.date) -> DaySales
def sales_panel(today: datetime.date) -> dict | None
    # None when settings.SQUARE_ACCESS_TOKEN is blank; else
    # {"yesterday": DaySales, "last_week": DaySales, "has_pulls": bool}
def pull_status(day: datetime.date) -> str   # "OK" | "FAILED" | "MISSING" from the latest SalesPull for the day
```

- `build_smart_alerts(..., square_pull_status: str | None = None, square_sync_failures: int = 0)`. `None` means Square is disabled → no Square alerts. `"FAILED"` → `{"id": "square-pull-failed", "type": "warning", "message": "Yesterday's Square sales pull failed"}`; `"MISSING"` → `{"id": "square-pull-missing", "type": "warning", "message": "No Square sales pull ran yesterday"}`. `square_sync_failures > 0` → `{"id": "square-sync-failed", "type": "warning", "message": f"{n} run{'s' if n != 1 else ''} failed to sync to Square"}`.
- `HomeView` passes `square_pull_status=pull_status(today - 1 day) if settings.SQUARE_ACCESS_TOKEN else None`, `square_sync_failures=SquareItem.objects.filter(deleted_at__isnull=True).exclude(last_error="").count()`, and `ctx["sales_panel"] = sales_panel(today)`.
- Panel card copy: label `Yesterday's Sales`, value `$<gross>`, sub-line `<tickets> tickets · $<concessions> concessions`, second sub-line `Last <weekday>: $<gross> · <tickets> tickets`. Empty state when `has_pulls` is false: value `—`, sub-line `No sales pulled yet.` Format dollars with `floatformat:2` on a `gross_dollars` property, or precompute strings in `sales_panel`; pick one.

- [ ] **Step 1: Write the failing tests**

`test_reports.py` append:

```python
class SalesPanelTests(TestCase):
    @override_settings(SQUARE_ACCESS_TOKEN="")
    def test_none_when_disabled(self) -> None:
        self.assertIsNone(sales_panel(datetime.date(2026, 10, 9)))

    @override_settings(SQUARE_ACCESS_TOKEN="tok")
    def test_yesterday_and_same_weekday_last_week(self) -> None:
        # lines on Oct 8 (ticket 1600 + popcorn 500) and Oct 1 (ticket 800)
        panel = sales_panel(datetime.date(2026, 10, 9))
        self.assertEqual(panel["yesterday"], DaySales(2100, 2, 500))
        self.assertEqual(panel["last_week"], DaySales(800, 1, 0))

class PullStatusTests(TestCase):
    def test_missing_failed_ok(self) -> None: ...  # no row → MISSING; FAILED row → FAILED; later OK row → OK
```

`test_smart_alerts.py` append:

```python
    def test_square_alerts(self) -> None:
        ids = [a["id"] for a in build_smart_alerts([], 1, self.today, square_pull_status="FAILED",
                                                   square_sync_failures=2)]
        self.assertIn("square-pull-failed", ids); self.assertIn("square-sync-failed", ids)
        self.assertEqual(
            [a for a in build_smart_alerts([], 1, self.today, square_pull_status="MISSING")][0]["message"],
            "No Square sales pull ran yesterday")
        self.assertEqual([a["id"] for a in build_smart_alerts([], 1, self.today, square_pull_status=None)
                          if a["id"].startswith("square")], [])
```

`test_home.py` append:

```python
    @override_settings(SQUARE_ACCESS_TOKEN="")
    def test_sales_panel_hidden_without_token(self) -> None:
        html = self.client.get(reverse("dashboard:home")).content.decode()
        self.assertNotIn("Yesterday's Sales", html)

    @override_settings(SQUARE_ACCESS_TOKEN="tok")
    def test_sales_panel_empty_state(self) -> None:
        html = self.client.get(reverse("dashboard:home")).content.decode()
        self.assertIn("No sales pulled yet", html)
```

- [ ] **Step 2: Run tests to verify they fail**
- [ ] **Step 3: Implement.**
- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/python manage.py test boxoffice dashboard -v 1`; lint `boxoffice dashboard/smart_alerts.py dashboard/tests/test_smart_alerts.py dashboard/tests/test_home.py`.

- [ ] **Step 5: Commit**

```bash
git add boxoffice dashboard
git commit -m "feat(dashboard): yesterday's sales panel and Square alerts on home"
```

---

### Task 13: Runbook, full verification

**Files:**
- Modify: `docs/superpowers/plans/cutover-runbook.md` (append a "Square sync" section)
- No code changes unless the full suite reveals one.

**Interfaces:** none.

- [ ] **Step 1: Append the Square section to the runbook**

Contents, in this order: the environment variables (`SQUARE_ACCESS_TOKEN`, `SQUARE_LOCATION_ID`, `SQUARE_TICKET_CATEGORY_ID`, `SQUARE_ENVIRONMENT=production`, `EMAIL_HOST`, `EMAIL_PORT`, `EMAIL_HOST_USER`, `EMAIL_HOST_PASSWORD`, `EMAIL_USE_TLS`, `DEFAULT_FROM_EMAIL`); the two cron lines for the Ansible repo's `webservers.yml`:

```
45 23 * * *  cd /srv/www_fortkentcinema_com && .venv/bin/python manage.py pull_square_sales
0  2  * * *  cd /srv/www_fortkentcinema_com && .venv/bin/python manage.py sync_square_catalog
```

(adjust the path to the deployed checkout); the admin steps (enter recipients, set the ticket report subject); and the spec's five rollout steps verbatim, including the dry-run commands.

- [ ] **Step 2: Run the full suite and lint**

Run: `.venv/bin/python manage.py test` and `.venv/bin/python -m flake8 boxoffice cinema/models/engagement.py cinema/admin.py dashboard/smart_alerts.py dashboard/tests/test_square_views.py`
Expected: all tests pass; no lint output.

- [ ] **Step 3: Smoke the commands with no token**

Run: `.venv/bin/python manage.py sync_square_catalog --dry-run` and `.venv/bin/python manage.py pull_square_sales --dry-run`
Expected: each prints the disabled line and exits 0.

- [ ] **Step 4: Commit**

```bash
git add docs/superpowers/plans/cutover-runbook.md
git commit -m "docs(boxoffice): Square sync runbook section"
```
