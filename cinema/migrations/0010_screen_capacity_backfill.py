"""Backfill placeholder Screen.capacity values.

The logic lives in cinema/screen_capacity.py so it can be tested; see the
docstring there for why.
"""

from cinema.screen_capacity import backfill_placeholder_capacity
from django.db import migrations


def backfill(apps, schema_editor):
    Screen = apps.get_model("cinema", "Screen")
    backfill_placeholder_capacity(Screen.objects)


def unbackfill(apps, schema_editor):
    # Deliberately a no-op: reverting to capacity=1 would restore bad data.
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("cinema", "0009_sponsorshipinquiry"),
    ]

    operations = [
        migrations.RunPython(backfill, unbackfill),
    ]
