"""Exercise migration 0005's actual data-copy path.

Every other test in this app creates its `MembershipTerm` rows after the
whole migration history has already run, so `MembershipTerm` is always
empty when 0005 applies — `slug_to_fk` and `fk_to_slug` never iterate a
single row. That blindness is how a broken reverse migration (RemoveField's
reversal re-adding a NOT NULL `tier` CharField onto a populated table,
before `fk_to_slug` ever runs) survived review once already. This test
builds real pre-existing rows at 0004, migrates forward through 0005, then
back down again, and checks both directions actually preserve the data.

Runs against a real schema-mutating migration, hence TransactionTestCase
rather than TestCase — a plain TestCase wraps each test in a transaction
that fights schema changes.

Two things keep this class from poisoning the rest of the run, which it
once did:

* It always puts the database back at the latest migration of every app,
  read from the loader rather than hard-coded. Migrating audience back to
  0004 unapplies everything after it, not just 0005; restoring only to
  0005 left later TransactionTestCase and LiveServerTestCase classes on a
  schema missing columns, and a `--keepdb` database stranded there.

* It creates the catalogue rows it needs instead of trusting 0004's seed
  to still be there. Every TransactionTestCase flushes on teardown, so
  under `--reverse`, `--shuffle`, or with the e2e live-server tests ahead
  of it, the seeded tiers are already gone by the time this runs.
  `serialized_rollback` would not fix that under `--keepdb`, which
  serializes whatever a previous run's flush left — nothing.

* It puts the seeded catalogue back after its own teardown flush. Plain
  TestCase classes rely on those rows, and under `--keepdb` the next run
  starts from whatever this class left behind.
"""

import datetime
from decimal import Decimal
from importlib import import_module

from django.apps import apps as django_apps
from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.test import TransactionTestCase

SEED = import_module("audience.migrations.0004_seed_membership_catalogue")
ALLOWANCES = import_module("audience.migrations.0007_seed_free_admission_allowances")


def latest_migrations(executor: MigrationExecutor) -> list[tuple[str, str]]:
    """Every app's leaf migration — where the test run expects the schema."""
    executor.loader.build_graph()
    return executor.loader.graph.leaf_nodes()


class MembershipTermMigrationTests(TransactionTestCase):
    migrate_from = [("audience", "0004_seed_membership_catalogue")]
    migrate_to = [("audience", "0005_membershipterm_tier_fk")]

    def setUp(self) -> None:
        self.executor = MigrationExecutor(connection)
        # Registered before anything can fail, so even an error in the
        # middle of a migration leaves the next test on the current schema.
        self.addCleanup(self.restore_latest_schema)

    def _fixture_teardown(self) -> None:
        # TransactionTestCase empties every table here; reseed what the
        # migrations seeded, as a freshly migrated database would have it.
        super()._fixture_teardown()
        SEED.seed(django_apps, None)
        ALLOWANCES.set_allowances(django_apps, None)

    def restore_latest_schema(self) -> None:
        executor = MigrationExecutor(connection)
        executor.migrate(latest_migrations(executor))

    def migrate(self, targets):
        self.executor.migrate(targets)
        self.executor.loader.build_graph()
        return self.executor.loader.project_state(targets).apps

    def build_rows_at_0004(self) -> None:
        old_apps = self.migrate(self.migrate_from)
        Tier = old_apps.get_model("audience", "MembershipTier")
        Member = old_apps.get_model("audience", "Member")
        MembershipTerm = old_apps.get_model("audience", "MembershipTerm")

        # The catalogue as 0004 seeds it, recreated where a flush removed
        # it. Every tier, not just the two the terms use: restoring the
        # schema runs 0007, which refuses to proceed without its tiers.
        for spec in SEED.TIERS:
            fields = {k: v for k, v in spec.items() if k not in ("slug", "benefits")}
            Tier.objects.get_or_create(slug=spec["slug"], defaults=fields)

        member = Member.objects.create(
            first_name="Ada", last_name="Byron", email="ada@example.com"
        )
        self.term_a_pk = MembershipTerm.objects.create(
            member=member,
            tier="cinema-supporter",
            started_on=datetime.date(2025, 1, 1),
            expires_on=datetime.date(2025, 12, 31),
            price_paid=Decimal("35.00"),
        ).pk
        self.term_b_pk = MembershipTerm.objects.create(
            member=member,
            tier="silver-screen",
            started_on=datetime.date(2026, 1, 1),
            expires_on=datetime.date(2026, 12, 31),
            price_paid=Decimal("150.00"),
        ).pk

    def round_trip(self) -> None:
        self.build_rows_at_0004()

        # Forward: 0004 -> 0005. slug_to_fk should match each term's slug
        # string to the seeded MembershipTier and preserve everything else.
        new_apps = self.migrate(self.migrate_to)
        Term = new_apps.get_model("audience", "MembershipTerm")
        Tier = new_apps.get_model("audience", "MembershipTier")

        supporter = Tier.objects.get(slug="cinema-supporter")
        silver = Tier.objects.get(slug="silver-screen")

        term_a = Term.objects.get(pk=self.term_a_pk)
        term_b = Term.objects.get(pk=self.term_b_pk)

        self.assertEqual(term_a.tier_id, supporter.pk)
        self.assertEqual(term_b.tier_id, silver.pk)
        self.assertEqual(term_a.price_paid, Decimal("35.00"))
        self.assertEqual(term_a.started_on, datetime.date(2025, 1, 1))
        self.assertEqual(term_a.expires_on, datetime.date(2025, 12, 31))
        self.assertEqual(term_b.price_paid, Decimal("150.00"))
        self.assertEqual(term_b.started_on, datetime.date(2026, 1, 1))
        self.assertEqual(term_b.expires_on, datetime.date(2026, 12, 31))

        # Backward: 0005 -> 0004. fk_to_slug must write the real slugs back
        # into the restored CharField — this is the assertion that would
        # have caught the NOT NULL crash in RemoveField's reversal.
        old_apps = self.migrate(self.migrate_from)
        OldTerm = old_apps.get_model("audience", "MembershipTerm")

        old_term_a = OldTerm.objects.get(pk=self.term_a_pk)
        old_term_b = OldTerm.objects.get(pk=self.term_b_pk)

        self.assertEqual(old_term_a.tier, "cinema-supporter")
        self.assertEqual(old_term_b.tier, "silver-screen")
        self.assertEqual(old_term_a.price_paid, Decimal("35.00"))
        self.assertEqual(old_term_b.price_paid, Decimal("150.00"))

    def test_forward_then_backward_round_trips_the_tier_data(self) -> None:
        self.round_trip()

    def test_round_trip_does_not_need_the_seed_to_survive_a_flush(self) -> None:
        # What an earlier TransactionTestCase's teardown leaves behind.
        from audience.models import MembershipBenefit, MembershipTier

        MembershipTier.objects.all().delete()
        MembershipBenefit.objects.all().delete()
        self.round_trip()

    def test_restores_every_app_to_its_latest_migration(self) -> None:
        self.round_trip()
        self.restore_latest_schema()

        executor = MigrationExecutor(connection)
        self.assertEqual(executor.migration_plan(latest_migrations(executor)), [])
