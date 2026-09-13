"""Pin /membership/'s query count.

Separate from test_membership_catalogue.py, which is a byte-for-byte
characterization test left untouched across the whole refactor. This file
only pins the query budget: 2 queries — one for the tiers
(show_on_membership_page=True) and one for the prefetched benefits — a
number that must not grow as tiers or benefits are added.
"""

from django.test import TestCase
from django.urls import reverse


class MembershipPageQueryCountTests(TestCase):
    def test_query_count_is_fixed(self) -> None:
        with self.assertNumQueries(2):
            self.client.get(reverse("membership"))
