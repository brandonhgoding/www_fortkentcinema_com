"""The ticket tiers sold online, in the order the Buy page and emails show them.

Kept apart from boxoffice.spec.SQUARE_TIERS (the variations on every Square
ticket item) on purpose: today the two lists match, and every online tier is
rung through its Square variation, but a tier with no SKU (member sign-in)
would be added here only.
"""

ONLINE_TIERS = ("adult", "senior", "child")
