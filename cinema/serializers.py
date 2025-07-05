from rest_framework import serializers

from cinema.models import Booking, Film, ScreeningTime


class ScreeningTimeSerializer(serializers.ModelSerializer):
    class Meta:
        model = ScreeningTime
        fields = ["date", "time", "is_matinee"]


class BookingSerializer(serializers.ModelSerializer):

    class Meta:
        model = Booking
        fields = [
            "booking_start_date",
            "booking_end_date",
            "is_active",
            "is_confirmed",
        ]


class FilmSerializer(serializers.ModelSerializer):
    bookings = BookingSerializer(many=True, read_only=True)

    class Meta:
        model = Film
        fields = ["id", "slug", "title", "imdb_id", "youtube_id", "omdb_json", "bookings"]


class FilmCalendarSerializer(serializers.ModelSerializer):
    bookings = BookingSerializer(many=True, read_only=True)

    class Meta:
        model = Film
        fields = ["id", "title", "bookings"]


class FilmArchiveSerializer(serializers.ModelSerializer):

    class Meta:
        model = Film
        fields = ["id", "slug", "title", "omdb_json"]


