# Recipient addresses are stored lowercased from now on (the unique
# constraint is case-sensitive, so "Owner@" and "owner@" were two rows).
# A row that would collide with an existing lowercase twin is left alone
# for the owner to remove in the admin.

from django.db import migrations


def lowercase_addresses(apps, schema_editor):
    EmailRecipient = apps.get_model("boxoffice", "EmailRecipient")
    for recipient in EmailRecipient.objects.all():
        wanted = recipient.address.strip().lower()
        if wanted == recipient.address:
            continue
        taken = EmailRecipient.objects.filter(
            report_id=recipient.report_id, address=wanted).exists()
        if not taken:
            recipient.address = wanted
            recipient.save(update_fields=["address"])


class Migration(migrations.Migration):

    dependencies = [
        ("boxoffice", "0012_saleline_show_date"),
    ]

    operations = [
        migrations.RunPython(lowercase_addresses, migrations.RunPython.noop),
    ]
