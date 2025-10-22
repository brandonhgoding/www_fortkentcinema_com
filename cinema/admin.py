from django.contrib import admin

from cinema.models import Booking, Event, Film, ScreeningTime, FilmGenre


class ScreeningTimeInline(admin.TabularInline):
    model = ScreeningTime
    extra = 0


class BookingAdmin(admin.ModelAdmin):
    inlines = [ScreeningTimeInline]


admin.site.register(Event)
admin.site.register(Film)
admin.site.register(FilmGenre)
admin.site.register(Booking, BookingAdmin)
