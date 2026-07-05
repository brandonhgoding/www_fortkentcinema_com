# cinema/models/screen.py
from django.db import models


class Screen(models.Model):
    name = models.CharField(max_length=100)  # "Screen 1", "Main", etc.
    capacity = models.PositiveIntegerField()

    SCREEN_TYPES = [
        ("standard", "Standard"),
        ("imax", "IMAX"),
        ("dolby_cinema", "Dolby Cinema"),
    ]
    screen_type = models.CharField(
        choices=SCREEN_TYPES, default="standard", max_length=12
    )

    ASPECT_RATIOS = [
        ("flat", "Flat (1.85:1)"),
        ("scope", "Scope (2.39:1)"),
        ("imax_190", "IMAX 1.90:1"),
        ("imax_143", "IMAX 1.43:1"),
    ]
    aspect_ratio = models.CharField(
        choices=ASPECT_RATIOS, max_length=8, default="scope"
    )

    SOUND_SYSTEMS = [
        ("standard", "Standard Surround"),
        ("dolby_digital", "Dolby Digital"),
        ("dolby_atmos", "Dolby Atmos"),
    ]
    sound_system = models.CharField(
        choices=SOUND_SYSTEMS, max_length=13, default="standard"
    )

    supports_3d = models.BooleanField(default=False)

    class Meta:
        ordering = ["name"]

    def __str__(self) -> str:
        return self.name
