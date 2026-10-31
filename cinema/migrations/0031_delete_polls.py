"""The film vote was retired 2026-10-31: polls, their options and votes go,
along with their content types and the permissions granted on them.
"""

from django.db import migrations


def forget_poll_models(apps, schema_editor):
    ContentType = apps.get_model("contenttypes", "ContentType")
    # Cascades to the permissions and their group and user grants.
    ContentType.objects.filter(
        app_label="cinema", model__in=["poll", "polloption", "vote"]
    ).delete()


class Migration(migrations.Migration):

    dependencies = [
        ("cinema", "0030_drop_online_tickets"),
        ("contenttypes", "0002_remove_content_type_name"),
    ]

    operations = [
        migrations.RunPython(forget_poll_models, migrations.RunPython.noop),
        # Children first: votes point at options and polls, options at polls.
        migrations.DeleteModel(name="Vote"),
        migrations.DeleteModel(name="PollOption"),
        migrations.DeleteModel(name="Poll"),
    ]
