"""A member with a term, and the paid order that bought it."""

import datetime
from decimal import Decimal
from audience.models import Member, MembershipTerm, MembershipTier

from join.models import MembershipOrder
from join.tests.factories import make_order

STARTED = datetime.date(2026, 10, 26)
EXPIRES = datetime.date(2027, 10, 25)


def paid_order(*, earlier_term: bool = False, **over) -> MembershipOrder:
    tier = MembershipTier.objects.get(slug="individual")
    member = Member.objects.create(first_name="Ann", last_name="Lee",
                                   email="ann@example.com")
    if earlier_term:
        MembershipTerm.objects.create(
            member=member, tier=tier, started_on=STARTED.replace(year=2025),
            expires_on=EXPIRES.replace(year=2026), price_paid=Decimal("60"))
    term = MembershipTerm.objects.create(
        member=member, tier=tier, started_on=STARTED, expires_on=EXPIRES,
        price_paid=Decimal("60"))
    fields = {"status": "PAID", "term": term}
    fields.update(over)
    return make_order(**fields)
