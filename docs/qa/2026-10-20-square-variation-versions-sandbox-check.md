# Square catalog: variation versions and poster survival (sandbox check)

Main at `fb77166`. Review item M2 (variation versions) and a live check of
M1 (`docs/superpowers/plans/2026-10-05-square-sync.md` for the sync design;
the 2026-10-20 box office review for the findings).

The sync stamps every existing variation with the *item's* version on an
update (`boxoffice/gateway.py`, `_variation_object`). Square's docs say an
item-only update bumps the item's version but not its variations'. If Square
also enforces the version on nested objects, the second rename after a push
is refused with `VERSION_MISMATCH` and the push lands in `last_error`.
Nothing in the sandbox has exercised two consecutive updates yet.

M1 (committed `fb77166`) sends the item's `image_ids` on every update so a
rename keeps the poster. That fix follows Square's documented
replace-on-update rule but has not been observed live; this check reads
`image_ids` back after each rename, so one session answers both.

Needs: `.env` with the sandbox settings (`SQUARE_ENVIRONMENT=sandbox`, the
sandbox token, location and Movies category), and a confirmed demo run that
already shows a green Square pill. Not engagement 4, which has no item on
purpose. If the run has no poster attached yet, run
`python manage.py sync_square_catalog` once first so the nightly image pass
attaches one.

---

## Steps

- [ ] **1.** In `python manage.py shell`, with `PK` set to the demo run:

```python
from boxoffice.gateway import get_gateway
from boxoffice.sync import push
from cinema.models import Engagement

gw = get_gateway()
eng = Engagement.objects.get(pk=PK)

def versions(item):
    obj = gw.client.catalog.object.get(item.square_id).object
    print("item", obj.version, "image_ids", obj.item_data.image_ids)
    print([(v.item_variation_data.sku, v.version)
           for v in obj.item_data.variations])

item = push(eng, gw); print(item.version, repr(item.last_error)); versions(item)
```

- [ ] **2.** First rename (the decisive read is the `versions` output):

```python
eng.display_title = eng.title + " v2"; eng.save()
item = push(eng, gw); print(item.version, repr(item.last_error)); versions(item)
```

- [ ] **3.** Second rename:

```python
eng.display_title = eng.display_title.replace(" v2", " v3"); eng.save()
item = push(eng, gw); print(item.version, repr(item.last_error)); versions(item)
```

- [ ] **4.** Put the title back:

```python
eng.display_title = ""; eng.save(); push(eng, gw)
```

- [ ] **5.** Record the three `versions` outputs and any `last_error` in the
      Findings table.

## Reading the result (M2)

- **After step 2 the variation versions equal the item's new version.**
  Square bumps nested objects together. No bug; close M2.
- **The variation versions stayed at the old value, and step 3 left
  `last_error` containing `VERSION_MISMATCH`.** The bug is real. Fix: store a
  version per variation (`SquareVariation.version`, read from
  `retrieve_item`) and send each variation its own. A warning about the item
  being "edited outside Django" on step 3 is the retry path firing; ignore it.
- **The variation versions stayed old but step 3 succeeded.** Square ignores
  nested versions on an update. No bug; note it in the gateway so nobody
  "fixes" it later.

## Reading the result (M1)

- `image_ids` prints the same id after steps 2 and 3 → the poster fix holds.
- `image_ids` prints empty after step 2 → the fix needs another look; report
  the exact output. Re-run `sync_square_catalog` afterwards to re-attach.

## Findings

| # | Step | What happened | Expected | Severity (blocks launch / fix soon / note) |
|---|------|---------------|----------|---------------------------------------------|
| 1 | 2 | Owner ran the check 2026-10-20: the rename pushed with no `last_error`. | push succeeds | note |
| 2 | 3 | Second rename pushed with no `last_error`; no `VERSION_MISMATCH`. | push succeeds | note |

## Result (2026-10-20)

The owner reports the sandbox session worked well: both renames went through.
M2 is closed with no code change; the gateway's `_variation_object` carries a
note so the item-version stamping is not "fixed" later. The `versions` and
`image_ids` outputs were not pasted back, so whether Square bumped the
variation versions alongside the item's, and the M1 poster read-back, are
not recorded here.
