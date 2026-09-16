"""Set the monthly free-admission allowance on the two tiers that grant one.

Confirmed 2026-09-15: only Cinema Supporter (1) and Family Plus (4). The
other three keep the field's default of 0.

Written as an update rather than folded into 0004's seed because 0004 has
already run everywhere this ships; a tier's allowance is editable in the
admin afterwards, so this sets a starting point rather than a truth.
"""

from django.db import migrations

ALLOWANCES = {
    "cinema-supporter": 1,
    "family-plus": 4,
}


def set_allowances(apps, schema_editor):
    Tier = apps.get_model("audience", "MembershipTier")
    for slug, allowance in ALLOWANCES.items():
        updated = Tier.objects.filter(slug=slug).update(
            free_admissions_per_month=allowance
        )
        if updated != 1:
            raise RuntimeError(
                f"Expected exactly one MembershipTier with slug={slug!r}, "
                f"found {updated}. The free-admission feature depends on "
                "this seed; fix the slug (here or on the tier) before "
                "re-running this migration."
            )


def clear_allowances(apps, schema_editor):
    Tier = apps.get_model("audience", "MembershipTier")
    Tier.objects.filter(slug__in=ALLOWANCES).update(
        free_admissions_per_month=0
    )


class Migration(migrations.Migration):

    dependencies = [
        ("audience", "0006_membershiptier_free_admissions_per_month"),
    ]

    operations = [
        migrations.RunPython(set_allowances, clear_allowances),
    ]
