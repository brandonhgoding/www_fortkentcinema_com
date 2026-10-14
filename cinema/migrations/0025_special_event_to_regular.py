from django.db import migrations


def special_event_to_regular(apps, schema_editor) -> None:
    Engagement = apps.get_model("cinema", "Engagement")
    Engagement.objects.filter(kind="SPECIAL_EVENT").update(kind="REGULAR")


class Migration(migrations.Migration):
    dependencies = [("cinema", "0024_remove_sponsorship")]

    operations = [
        # The reverse is a no-op: once merged, nothing can tell which Regular
        # rows used to be Special Events.
        migrations.RunPython(special_event_to_regular, migrations.RunPython.noop),
    ]
