from django.core.management.base import BaseCommand

from cinema.services.square_catalog import sync_bookings_and_showtimes_to_square


class Command(BaseCommand):
    help = "Sync Bookings and ScreeningTimes to Square (Booking -> Item, Showtime -> Item Variation)."

    def handle(self, *args, **options):
        sync_bookings_and_showtimes_to_square()
        self.stdout.write(self.style.SUCCESS("Square bookings/showtimes sync completed."))
