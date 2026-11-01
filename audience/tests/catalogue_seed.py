"""Reseed the membership catalogue after a TransactionTestCase flush.

Migration tests run against a real schema and TransactionTestCase empties
every table afterwards, so they put back what the seed migrations created,
as a freshly migrated database would have it. By teardown the schema is the
latest one again, so the seed runs against the current models, and fields
its rows name that the model has since dropped (checkout_url, 2026-11-01)
are left out.
"""

from importlib import import_module
from unittest import mock

from django.apps import apps as django_apps

SEED = import_module("audience.migrations.0004_seed_membership_catalogue")
ALLOWANCES = import_module("audience.migrations.0007_seed_free_admission_allowances")


def reseed_catalogue() -> None:
    Tier = django_apps.get_model("audience", "MembershipTier")
    known = {f.name for f in Tier._meta.get_fields()} | {"benefits"}
    tiers = [{k: v for k, v in spec.items() if k in known} for spec in SEED.TIERS]
    with mock.patch.object(SEED, "TIERS", tiers):
        SEED.seed(django_apps, None)
    ALLOWANCES.set_allowances(django_apps, None)
