import datetime
from datetime import date
from decimal import Decimal
from unittest import mock
from zoneinfo import ZoneInfo

from audience.models import Member, MembershipTerm, MembershipTier
from boxoffice.gateway import GatewayError, OrderData, OrderLine, Recipient
from boxoffice.memberships import order_never_fetched, process_order, split_name
from boxoffice.models import MembershipSale
from boxoffice.tests.fakes import FakeGateway
from django.test import SimpleTestCase, TestCase, override_settings

INDIVIDUAL = "LUXWXSDRQGNENE7XDBXPNYXY"
FAMILY = "VAR-FAMILY"
TICKET = "TICKET-VAR"
ANN = Recipient("Ann Lee", "Ann@Example.com ", "+12075550100")


def at_eastern(*parts) -> datetime.datetime:
    return datetime.datetime(*parts, tzinfo=ZoneInfo("America/New_York"))


def ticket_line(uid="L2") -> OrderLine:
    return OrderLine(uid=uid, name="Dune", variation_name="Adult",
                     catalog_object_id=TICKET, quantity=2, gross_cents=1600)


class MembershipOrderTestCase(TestCase):
    def setUp(self):
        MembershipTier.objects.filter(slug="individual").update(
            square_variation_id=INDIVIDUAL)
        self.gw = FakeGateway()

    def membership_order(self, order_id="O1",
                         closed_at=at_eastern(2026, 10, 2, 19, 12), quantity=1,
                         recipient=ANN, extra_lines=(), gross_cents=None,
                         gateway=None) -> OrderData:
        if gross_cents is None:
            gross_cents = 6000 * quantity
        line = OrderLine(uid="L1", name="Individual Membership",
                         variation_name="Annual", catalog_object_id=INDIVIDUAL,
                         quantity=quantity, gross_cents=gross_cents)
        order = OrderData(order_id=order_id, closed_at=closed_at,
                          lines=(line, *extra_lines), recipient=recipient)
        (gateway or self.gw).orders.append(order)
        return order


class SplitNameTests(SimpleTestCase):
    def test_splits_on_the_last_space(self):
        self.assertEqual(split_name("Mary Ann Smith Jr."), ("Mary Ann Smith", "Jr."))

    def test_one_word_is_all_first_name(self):
        self.assertEqual(split_name(" Cher "), ("Cher", ""))

    def test_blank_stays_blank(self):
        self.assertEqual(split_name("  "), ("", ""))


class OrderNeverFetchedTests(SimpleTestCase):
    def test_failed_without_closed_at_was_never_fetched(self):
        sale = MembershipSale(order_id="O1", status="FAILED", closed_at=None)
        self.assertTrue(order_never_fetched(sale))

    def test_attribution_failure_was_fetched(self):
        sale = MembershipSale(order_id="O1", status="FAILED",
                              closed_at=at_eastern(2026, 10, 2, 19, 12))
        self.assertFalse(order_never_fetched(sale))

    def test_ok_sale_was_fetched(self):
        sale = MembershipSale(order_id="O1", status="OK", closed_at=None)
        self.assertFalse(order_never_fetched(sale))


class NewMemberTests(MembershipOrderTestCase):
    def test_creates_member_and_term(self):
        self.membership_order()
        sale = process_order("O1", self.gw)
        member = Member.objects.get(email="ann@example.com")
        self.assertEqual((member.first_name, member.last_name, member.phone),
                         ("Ann", "Lee", "+12075550100"))
        term = member.terms.get()
        self.assertEqual((term.tier.slug, term.started_on, term.expires_on),
                         ("individual", date(2026, 10, 2), date(2027, 10, 1)))
        self.assertEqual((term.price_paid, term.purchased_at, term.notes),
                         (Decimal("60.00"), date(2026, 10, 2), "Square order O1"))
        self.assertEqual(
            (sale.status, sale.term, sale.tier.slug, sale.quantity, sale.gross_cents),
            ("OK", term, "individual", 1, 6000))
        self.assertEqual((sale.display_name, sale.email, sale.phone),
                         ("Ann Lee", "ann@example.com", "+12075550100"))
        self.assertEqual(sale.error, "")
        self.assertIsNotNone(sale.processed_at)
        stored = MembershipSale.objects.get()
        self.assertEqual((stored.pk, stored.status, stored.term), (sale.pk, "OK", term))

    def test_late_evening_utc_lands_on_the_eastern_day(self):
        # 03:12 UTC on 3 October is 23:12 Eastern on 2 October.
        self.membership_order(closed_at=datetime.datetime(
            2026, 10, 3, 3, 12, tzinfo=datetime.timezone.utc))
        process_order("O1", self.gw)
        term = MembershipTerm.objects.get()
        self.assertEqual((term.started_on, term.purchased_at),
                         (date(2026, 10, 2), date(2026, 10, 2)))

    def test_price_paid_is_the_gross_not_the_list_price(self):
        self.membership_order(gross_cents=4500)
        sale = process_order("O1", self.gw)
        self.assertEqual(sale.gross_cents, 4500)
        self.assertEqual(MembershipTerm.objects.get().price_paid, Decimal("45.00"))

    def test_name_splits_on_the_last_space(self):
        self.membership_order(recipient=Recipient(
            "Mary Ann Smith Jr.", "mary@example.com", ""))
        self.membership_order(order_id="O2", recipient=Recipient(
            "Cher", "cher@example.com", ""))
        process_order("O1", self.gw)
        process_order("O2", self.gw)
        mary = Member.objects.get(email="mary@example.com")
        cher = Member.objects.get(email="cher@example.com")
        self.assertEqual((mary.first_name, mary.last_name), ("Mary Ann Smith", "Jr."))
        self.assertEqual((cher.first_name, cher.last_name), ("Cher", ""))

    def test_membership_with_tickets_in_the_same_order(self):
        self.membership_order(extra_lines=(ticket_line(),))
        sale = process_order("O1", self.gw)
        self.assertEqual((sale.status, sale.quantity, sale.gross_cents),
                         ("OK", 1, 6000))
        self.assertEqual(MembershipTerm.objects.count(), 1)


class ExistingMemberTests(MembershipOrderTestCase):
    def setUp(self):
        super().setUp()
        self.member = Member.objects.create(
            first_name="Ann", last_name="Lee", email="ann@example.com", phone="")
        self.term = MembershipTerm.objects.create(
            member=self.member, tier=MembershipTier.objects.get(slug="individual"),
            started_on=date(2026, 1, 15), expires_on=date(2027, 1, 14),
            price_paid=Decimal("60"))

    def new_term(self):
        return self.member.terms.exclude(pk=self.term.pk).get()

    def test_active_member_renews_after_cover_ends(self):
        self.membership_order()
        sale = process_order("O1", self.gw)
        term = self.new_term()
        self.assertEqual((term.started_on, term.expires_on),
                         (date(2027, 1, 15), date(2028, 1, 14)))
        self.assertEqual(term.purchased_at, date(2026, 10, 2))
        self.assertEqual((sale.status, sale.term), ("OK", term))

    def test_lapsed_member_renews_on_the_purchase_date(self):
        self.term.started_on = date(2024, 1, 15)
        self.term.expires_on = date(2025, 1, 14)
        self.term.save()
        self.membership_order()
        process_order("O1", self.gw)
        term = self.new_term()
        self.assertEqual((term.started_on, term.expires_on),
                         (date(2026, 10, 2), date(2027, 10, 1)))

    def test_mixed_case_email_matches(self):
        self.membership_order(recipient=Recipient("Ann Lee", "ANN@example.com", ""))
        sale = process_order("O1", self.gw)
        self.assertEqual(Member.objects.count(), 1)
        self.assertEqual(self.member.terms.count(), 2)
        self.assertEqual(sale.email, "ann@example.com")

    def test_name_kept_phone_filled_only_when_blank(self):
        self.membership_order(recipient=Recipient(
            "A. Lee", "ann@example.com", "+12075550100"))
        process_order("O1", self.gw)
        self.member.refresh_from_db()
        self.assertEqual(
            (self.member.first_name, self.member.last_name, self.member.phone),
            ("Ann", "Lee", "+12075550100"))

        Member.objects.filter(pk=self.member.pk).update(phone="555")
        self.membership_order(order_id="O2", recipient=Recipient(
            "A. Lee", "ann@example.com", "+12075550199"))
        sale = process_order("O2", self.gw)
        self.member.refresh_from_db()
        self.assertEqual(self.member.phone, "555")
        self.assertEqual((sale.status, sale.phone), ("OK", "+12075550199"))

    def test_member_with_no_terms_starts_on_the_purchase_date(self):
        self.term.delete()
        self.membership_order()
        process_order("O1", self.gw)
        term = self.member.terms.get()
        self.assertEqual((term.started_on, term.expires_on),
                         (date(2026, 10, 2), date(2027, 10, 1)))

    def test_never_expiring_term_fails(self):
        self.term.expires_on = date.max
        self.term.save()
        self.membership_order()
        sale = process_order("O1", self.gw)
        self.assertEqual((sale.status, sale.error, sale.term),
                         ("FAILED", "Current term never expires", None))
        self.assertEqual(MembershipTerm.objects.count(), 1)
        self.assertEqual(MembershipSale.objects.get().status, "FAILED")

    def test_term_running_past_year_9999_fails(self):
        self.term.started_on = date(9998, 1, 1)
        self.term.expires_on = date(9999, 6, 30)
        self.term.save()
        self.membership_order()
        sale = process_order("O1", self.gw)
        self.assertEqual(sale.status, "FAILED")
        self.assertEqual(sale.error, "A 12-month term from 9999-07-01 runs past "
                                     "31 December 9999. Enter the term by hand.")
        self.assertEqual(MembershipTerm.objects.count(), 1)


class FailureTests(MembershipOrderTestCase):
    def test_quantity_two_fails_with_buyer_kept(self):
        self.membership_order(quantity=2)
        sale = process_order("O1", self.gw)
        self.assertEqual((sale.status, sale.error),
                         ("FAILED", "Ordered 2 memberships; enter by hand"))
        stored = MembershipSale.objects.get()
        self.assertEqual((stored.email, stored.display_name, stored.quantity,
                          stored.gross_cents, stored.tier.slug),
                         ("ann@example.com", "Ann Lee", 2, 12000, "individual"))
        self.assertEqual(Member.objects.count(), 0)
        self.assertEqual(MembershipTerm.objects.count(), 0)

    def test_two_membership_lines_fail(self):
        MembershipTier.objects.filter(slug="family").update(square_variation_id=FAMILY)
        family = OrderLine(uid="L2", name="Family Membership", variation_name="Annual",
                           catalog_object_id=FAMILY, quantity=1, gross_cents=15000)
        self.membership_order(extra_lines=(family,))
        sale = process_order("O1", self.gw)
        self.assertEqual((sale.status, sale.error),
                         ("FAILED", "Ordered 2 memberships; enter by hand"))
        self.assertEqual((sale.tier.slug, sale.quantity, sale.gross_cents),
                         ("individual", 2, 21000))
        self.assertEqual(Member.objects.count(), 0)
        self.assertEqual(MembershipTerm.objects.count(), 0)

    def test_no_email_is_skipped(self):
        self.membership_order(recipient=None)
        sale = process_order("O1", self.gw)
        self.assertEqual((sale.status, sale.error),
                         ("SKIPPED", "No buyer email (register sale)"))
        self.assertEqual(MembershipSale.objects.get().status, "SKIPPED")
        self.assertEqual(Member.objects.count(), 0)
        self.assertEqual(MembershipTerm.objects.count(), 0)

    def test_ticket_only_order_records_nothing(self):
        self.gw.orders.append(OrderData(order_id="O1",
                                        closed_at=at_eastern(2026, 10, 2, 19, 12),
                                        lines=(ticket_line(),)))
        self.assertIsNone(process_order("O1", self.gw))
        self.assertEqual(MembershipSale.objects.count(), 0)

    def test_gateway_error_fails_with_only_order_id(self):
        self.gw = FakeGateway(fail_with=GatewayError("boom"))
        sale = process_order("O1", self.gw)
        stored = MembershipSale.objects.get(order_id="O1")
        self.assertEqual((sale.pk, stored.status, stored.error),
                         (stored.pk, "FAILED",
                          "Could not fetch the order from Square: boom"))
        self.assertIsNone(stored.tier)
        self.assertIsNone(stored.closed_at)
        self.assertEqual(stored.email, "")
        self.assertIsNotNone(stored.processed_at)

    def test_gateway_disabled_fails(self):
        with mock.patch("boxoffice.memberships.get_gateway", return_value=None), \
                override_settings(SQUARE_ACCESS_TOKEN=""):
            sale = process_order("O1")
        stored = MembershipSale.objects.get(order_id="O1")
        self.assertEqual((sale.pk, stored.status, stored.error),
                         (stored.pk, "FAILED",
                          "Square sync disabled: no SQUARE_ACCESS_TOKEN"))
        self.assertIsNone(stored.tier)

    def test_failed_row_for_a_non_membership_order_is_removed(self):
        process_order("O1", FakeGateway(fail_with=GatewayError("boom")))
        self.assertEqual(MembershipSale.objects.get().status, "FAILED")
        self.gw.orders.append(OrderData(order_id="O1",
                                        closed_at=at_eastern(2026, 10, 2, 19, 12),
                                        lines=(ticket_line(),)))
        self.assertIsNone(process_order("O1", self.gw))
        self.assertEqual(MembershipSale.objects.count(), 0)

    def test_missing_closed_at_fails(self):
        self.membership_order(closed_at=None)
        sale = process_order("O1", self.gw)
        self.assertEqual((sale.status, sale.error),
                         ("FAILED", "Order has no closed_at"))
        self.assertEqual(MembershipSale.objects.get().status, "FAILED")
        self.assertEqual(Member.objects.count(), 0)

    def test_unexpected_exception_fails_and_logs(self):
        self.membership_order()
        with mock.patch("boxoffice.memberships.MembershipTerm.default_expiry",
                        side_effect=RuntimeError("x")), \
                self.assertLogs("boxoffice.memberships", "ERROR") as logs:
            sale = process_order("O1", self.gw)
        self.assertEqual((sale.status, sale.error), ("FAILED", "RuntimeError('x')"))
        self.assertEqual(MembershipSale.objects.get().status, "FAILED")
        self.assertIn("O1", logs.output[0])
        self.assertEqual(Member.objects.count(), 0)
        self.assertEqual(MembershipTerm.objects.count(), 0)


class IdempotencyTests(MembershipOrderTestCase):
    def retrieve_calls(self, gateway):
        return [c for c in gateway.calls if c[0] == "retrieve_order"]

    def test_second_call_for_an_ok_sale_does_nothing(self):
        self.membership_order()
        first = process_order("O1", self.gw)
        second = process_order("O1", self.gw)
        self.assertEqual((second.pk, second.status), (first.pk, "OK"))
        self.assertEqual(MembershipTerm.objects.count(), 1)
        self.assertEqual(len(self.retrieve_calls(self.gw)), 1)

    def test_ok_sale_with_deleted_term_is_not_reprocessed(self):
        self.membership_order()
        process_order("O1", self.gw)
        MembershipTerm.objects.all().delete()
        sale = process_order("O1", self.gw)
        self.assertEqual(MembershipTerm.objects.count(), 0)
        self.assertEqual((sale.status, sale.term), ("OK", None))

    def test_skipped_sale_is_not_reprocessed(self):
        self.membership_order(recipient=None)
        process_order("O1", self.gw)
        sale = process_order("O1", self.gw)
        self.assertEqual(sale.status, "SKIPPED")
        self.assertEqual(len(self.retrieve_calls(self.gw)), 1)
        self.assertEqual(Member.objects.count(), 0)

    def test_failed_sale_is_retried(self):
        failed = process_order("O1", FakeGateway(fail_with=GatewayError("boom")))
        self.assertEqual(failed.error, "Could not fetch the order from Square: boom")
        self.membership_order()
        sale = process_order("O1", self.gw)
        self.assertEqual((sale.pk, sale.status, sale.error), (failed.pk, "OK", ""))
        self.assertEqual(MembershipSale.objects.count(), 1)
        self.assertEqual(MembershipTerm.objects.count(), 1)

    def test_pre_existing_failed_row_is_reused(self):
        existing = MembershipSale.objects.create(order_id="O1", status="FAILED")
        self.membership_order()
        sale = process_order("O1", self.gw)
        self.assertEqual((sale.pk, sale.status), (existing.pk, "OK"))
        self.assertEqual(MembershipSale.objects.get().status, "OK")

    def test_event_arriving_mid_fetch_does_not_create_a_second_term(self):
        second_event_gw = FakeGateway()
        self.membership_order(gateway=second_event_gw)
        order = second_event_gw.orders[0]

        class SlowGateway(FakeGateway):
            def retrieve_order(self, order_id):
                # The second event finishes while this fetch is in flight.
                process_order(order_id, second_event_gw)
                return super().retrieve_order(order_id)

        slow = SlowGateway()
        slow.orders.append(order)
        sale = process_order("O1", slow)
        self.assertEqual(sale.status, "OK")
        self.assertEqual(MembershipTerm.objects.count(), 1)
        self.assertEqual(Member.objects.count(), 1)
        self.assertEqual(MembershipSale.objects.count(), 1)
        self.assertEqual(sale.term, MembershipTerm.objects.get())

    def test_failed_fetch_after_another_event_finished_keeps_the_sale(self):
        second_event_gw = FakeGateway()
        self.membership_order(gateway=second_event_gw)

        class FailingAfterGateway(FakeGateway):
            def retrieve_order(self, order_id):
                # The second event finishes, then this fetch fails.
                process_order(order_id, second_event_gw)
                raise GatewayError("boom")

        sale = process_order("O1", FailingAfterGateway())
        term = MembershipTerm.objects.get()
        stored = MembershipSale.objects.get()
        self.assertEqual((sale.status, sale.term), ("OK", term))
        self.assertEqual((stored.status, stored.error, stored.term, stored.email),
                         ("OK", "", term, "ann@example.com"))
