import datetime
from zoneinfo import ZoneInfo

from django.db import migrations

# The site's time zone (settings.TIME_ZONE), fixed here so the migration
# means the same thing if that setting ever changes.
SITE_TZ = ZoneInfo("America/New_York")


def backfill(apps, schema_editor):
    """Give drafts from before created_at existed a start day.

    BlogPost.date_for_publishing moves post_date to the publish day only
    while it still equals the day the draft was started, and these drafts
    had no start day, so they went out under their old date. The editor
    pre-filled post_date with today when a draft was started, so the start
    of post_date is the best record of that day.

    The limit: a draft whose date staff set on purpose before this existed
    (a backdated review) can't be told from one left alone, so publishing it
    moves it to the publish day too. Its date can be set back after
    publishing; saving a published post keeps its date.

    Published posts stay null: their date is the one they went out with.
    """
    BlogPost = apps.get_model("blog", "BlogPost")
    drafts = BlogPost.objects.filter(status="draft", created_at__isnull=True)
    for pk, post_date in drafts.values_list("pk", "post_date").iterator():
        started = datetime.datetime.combine(post_date, datetime.time.min, tzinfo=SITE_TZ)
        BlogPost.objects.filter(pk=pk).update(created_at=started)


class Migration(migrations.Migration):

    dependencies = [
        ("blog", "0022_blogpost_lead_text"),
    ]

    operations = [
        # Not reversed: a filled-in start can't be told from a real one taken
        # at midnight, and a start day does no harm on an older schema.
        migrations.RunPython(backfill, migrations.RunPython.noop),
    ]
