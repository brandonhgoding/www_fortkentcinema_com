# cinema/migrations/0005_populate_screeningtimes.py
import datetime

from django.db import migrations


def populate_screeningtimes(apps, schema_editor):
    Booking = apps.get_model("cinema", "Booking")
    ScreeningTime = apps.get_model("cinema", "ScreeningTime")

    # Define showtimes by weekday (0=Monday, 6=Sunday)
    showtimes = {
        2: ["19:30"],  # Wednesday
        3: ["19:30"],  # Thursday
        4: ["19:30"],  # Friday
        5: ["15:00", "19:30"],  # Saturday
        6: ["14:00", "17:00"],  # Sunday
    }

    for booking in Booking.objects.all():
        print("Populating screening times for booking:", booking.id)
        current_date = booking.booking_start_date
        while current_date <= booking.booking_end_date:
            weekday = current_date.weekday()
            times = showtimes.get(weekday, [])
            for t in times:
                hour, minute = map(int, t.split(":"))
                ScreeningTime.objects.create(
                    booking=booking, date=current_date, time=datetime.time(hour, minute)
                )
            current_date += datetime.timedelta(days=1)


class Migration(migrations.Migration):

    dependencies = [
        ("cinema", "0003_rename_playdate_screeningtime_alter_film_options"),
    ]

    operations = [
        migrations.RunPython(populate_screeningtimes),
    ]
