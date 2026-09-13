"""Turn MembershipTerm.tier from a slug string into a foreign key.

Four steps rather than one AlterField, which would cast varchar to integer
and drop every value it could not convert. Membership terms carry
price_paid; they are revenue records, not scratch data.
"""

import django.db.models.deletion
from django.db import migrations, models


def slug_to_fk(apps, schema_editor):
    Term = apps.get_model("audience", "MembershipTerm")
    Tier = apps.get_model("audience", "MembershipTier")
    by_slug = {t.slug: t for t in Tier.objects.all()}

    for term in Term.objects.exclude(tier="").iterator():
        tier = by_slug.get(term.tier)
        if tier is None:
            raise RuntimeError(
                f"MembershipTerm {term.pk} has tier {term.tier!r}, which matches "
                f"no MembershipTier. Refusing to guess. Known slugs: "
                f"{sorted(by_slug)}"
            )
        term.tier_fk = tier
        term.save(update_fields=["tier_fk"])


def fk_to_slug(apps, schema_editor):
    Term = apps.get_model("audience", "MembershipTerm")
    for term in Term.objects.select_related("tier_fk").iterator():
        term.tier = term.tier_fk.slug if term.tier_fk else ""
        term.save(update_fields=["tier"])


class Migration(migrations.Migration):

    dependencies = [
        ("audience", "0004_seed_membership_catalogue"),
    ]

    operations = [
        migrations.AddField(
            model_name="membershipterm",
            name="tier_fk",
            field=models.ForeignKey(
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="terms",
                to="audience.membershiptier",
            ),
        ),
        migrations.RunPython(slug_to_fk, fk_to_slug),
        migrations.RemoveField(model_name="membershipterm", name="tier"),
        migrations.RenameField(
            model_name="membershipterm", old_name="tier_fk", new_name="tier"
        ),
        migrations.AlterField(
            model_name="membershipterm",
            name="tier",
            field=models.ForeignKey(
                help_text="Retire a tier with show_on_membership_page instead "
                "of deleting it — terms are revenue records.",
                on_delete=django.db.models.deletion.PROTECT,
                related_name="terms",
                to="audience.membershiptier",
            ),
        ),
    ]
