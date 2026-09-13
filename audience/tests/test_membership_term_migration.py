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
"""

import datetime
from decimal import Decimal

from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.test import TransactionTestCase


class MembershipTermMigrationTests(TransactionTestCase):
    migrate_from = [("audience", "0004_seed_membership_catalogue")]
    migrate_to = [("audience", "0005_membershipterm_tier_fk")]

    def setUp(self) -> None:
        executor = MigrationExecutor(connection)
        executor.migrate(self.migrate_from)
        executor.loader.build_graph()

        old_apps = executor.loader.project_state(self.migrate_from).apps
        Member = old_apps.get_model("audience", "Member")
        MembershipTerm = old_apps.get_model("audience", "MembershipTerm")

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

        self.executor = executor

    def test_forward_then_backward_round_trips_the_tier_data(self) -> None:
        # Forward: 0004 -> 0005. slug_to_fk should match each term's slug
        # string to the seeded MembershipTier and preserve everything else.
        self.executor.migrate(self.migrate_to)
        self.executor.loader.build_graph()

        new_apps = self.executor.loader.project_state(self.migrate_to).apps
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
        self.executor.migrate(self.migrate_from)
        self.executor.loader.build_graph()

        old_apps = self.executor.loader.project_state(self.migrate_from).apps
        OldTerm = old_apps.get_model("audience", "MembershipTerm")

        old_term_a = OldTerm.objects.get(pk=self.term_a_pk)
        old_term_b = OldTerm.objects.get(pk=self.term_b_pk)

        self.assertEqual(old_term_a.tier, "cinema-supporter")
        self.assertEqual(old_term_b.tier, "silver-screen")
        self.assertEqual(old_term_a.price_paid, Decimal("35.00"))
        self.assertEqual(old_term_b.price_paid, Decimal("150.00"))

        # Leave the database migrated forward again so this test doesn't
        # strand later tests (or the next migrate) at an old schema.
        self.executor.migrate(self.migrate_to)
        self.executor.loader.build_graph()
