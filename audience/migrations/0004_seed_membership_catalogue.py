"""Seed the tier catalogue from what web.constants.MEMBERSHIP held.

The data is copied in rather than imported: `audience` must never import
`web` (web imports audience), and the constant is deleted later in this
same piece of work. A migration that reaches into application code stops
being reproducible the moment that code moves.
"""

from django.db import migrations

# name -> sort_order. Variants of a category share a value, which is what
# keeps every tier's perk list in the same order.
BENEFITS = [
    ("$2 off matinee tickets", 10),
    ("$1 off evening tickets", 20),
    ("$4 off evening tickets", 20),
    ("$1 off small popcorn", 30),
    ("$1 off medium & large popcorn", 40),
    ("$2 off medium & large popcorn", 40),
    ("Free small popcorn during your birthday month", 50),
    ("10% off rentals", 60),
    ("15% off rentals & parties", 60),
    ("20% off rentals & parties", 60),
]

COMMON = [
    "$2 off matinee tickets",
    "$4 off evening tickets",
    "$1 off small popcorn",
    "$2 off medium & large popcorn",
    "Free small popcorn during your birthday month",
]

TIERS = [
    {
        "slug": "silver-screen",
        "name": "Silver Screen",
        "eyebrow": "Seniors 65+",
        "price": 35,
        "featured": False,
        "is_family_tier": False,
        "checkout_url": "https://square.link/u/UnQLNeHp",
        "sort_order": 10,
        "benefits": [
            "$2 off matinee tickets",
            "$1 off evening tickets",
            "$1 off small popcorn",
            "$1 off medium & large popcorn",
            "Free small popcorn during your birthday month",
            "10% off rentals",
        ],
    },
    {
        "slug": "individual",
        "name": "Individual",
        "eyebrow": "",
        "price": 60,
        "featured": False,
        "is_family_tier": False,
        "checkout_url": "https://square.link/u/zricPsRR",
        "sort_order": 20,
        "benefits": COMMON + ["10% off rentals"],
    },
    {
        "slug": "cinema-supporter",
        "name": "Cinema Supporter",
        "eyebrow": "",
        "price": 120,
        "featured": True,
        "is_family_tier": False,
        "checkout_url": "https://square.link/u/2HnpAb9N",
        "sort_order": 30,
        "benefits": COMMON + ["15% off rentals & parties"],
    },
    {
        "slug": "family",
        "name": "Family",
        "eyebrow": "",
        "price": 150,
        "featured": False,
        "is_family_tier": True,
        "checkout_url": "https://square.link/u/FkcUasKu",
        "sort_order": 40,
        "benefits": COMMON + ["15% off rentals & parties"],
    },
    {
        "slug": "family-plus",
        "name": "Family Plus",
        "eyebrow": "",
        "price": 250,
        "featured": False,
        "is_family_tier": True,
        "checkout_url": "https://square.link/u/1YSgMFSQ",
        "sort_order": 50,
        "benefits": COMMON + ["20% off rentals & parties"],
    },
]


def seed(apps, schema_editor):
    Benefit = apps.get_model("audience", "MembershipBenefit")
    Tier = apps.get_model("audience", "MembershipTier")

    by_name = {}
    for name, sort_order in BENEFITS:
        by_name[name] = Benefit.objects.create(name=name, sort_order=sort_order)

    for spec in TIERS:
        # Copy rather than pop: TIERS is module-level, and popping would
        # mutate it for the life of the process. A reverse followed by a
        # re-apply — which `migrate` back and forward in one process does —
        # would then fail on the missing key.
        fields = {k: v for k, v in spec.items() if k != "benefits"}
        tier = Tier.objects.create(**fields)
        tier.benefits.set([by_name[n] for n in spec["benefits"]])


def unseed(apps, schema_editor):
    # Scoped to exactly what `seed` created — an unscoped delete would also
    # take any tier or benefit a staff member added since through the admin.
    #
    # Known limitation: benefits are matched by the names seeded here, so a
    # seeded perk renamed since (in the admin or the dashboard) survives a
    # rollback, orphaned from every tier. Benefits have no slug, and `seed`
    # never recorded the pks it created, so nothing stable identifies them
    # after a rename. Guessing — the lowest ten pks, say, or every benefit
    # a seeded tier carries — could delete perks staff added. Tiers do not
    # have this problem: their slugs are fixed after creation.
    apps.get_model("audience", "MembershipTier").objects.filter(
        slug__in=[spec["slug"] for spec in TIERS]
    ).delete()
    apps.get_model("audience", "MembershipBenefit").objects.filter(
        name__in=[name for name, _sort_order in BENEFITS]
    ).delete()


class Migration(migrations.Migration):

    dependencies = [
        ("audience", "0003_membershipbenefit_membershiptier"),
    ]

    operations = [
        migrations.RunPython(seed, unseed),
    ]
