"""Term-set questions that no single term can answer on its own.

`MembershipTerm` deliberately carries no overlap constraint: a legitimate
early renewal overlaps the term it renews, so the database must allow it.
That leaves double-entry — the same renewal keyed twice — looking exactly
like a normal renewal to the model. Telling them apart needs the whole set,
which is what lives here.
"""

import datetime
from collections.abc import Iterable


def overlapping_term_ids(terms: Iterable) -> set[int]:
    """Primary keys of terms whose dates overlap another term in `terms`.

    Callers pass one member's terms. Both terms in an overlapping pair are
    returned: the screen highlights the pair, because which of the two is
    the mistake is a judgement for whoever is looking, not for this code.

    Quadratic on purpose — a member has a handful of terms, and the pairwise
    loop reads as the definition of the thing rather than as a sweep that
    has to be re-derived to be trusted. It also works on unsaved or
    Python-filtered lists, which a SQL self-join would not.
    """
    terms = list(terms)
    overlapping: set[int] = set()
    for i, first in enumerate(terms):
        for second in terms[i + 1:]:
            if first.started_on <= second.expires_on and (
                second.started_on <= first.expires_on
            ):
                overlapping.add(first.pk)
                overlapping.add(second.pk)
    return overlapping


def renewal_start(latest, today: datetime.date) -> datetime.date:
    """When a renewal of `latest` should begin.

    An early renewal continues from the day after the current term expires,
    so the member keeps every day they paid for. A renewal taken after a
    lapse starts today instead — back-dating it would burn the new term
    against months the member was not a member.
    """
    return max(latest.expires_on + datetime.timedelta(days=1), today)
