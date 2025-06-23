from django.contrib import admin

from cinema.models import Booking, Film

# Register your models here.
admin.site.register(Film)
admin.site.register(Booking)
