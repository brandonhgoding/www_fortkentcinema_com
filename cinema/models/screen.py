# cinema/models/screen.py
from django.db import models


class Screen(models.Model):
    name = models.CharField(max_length=100)  # "Screen 1", "Main", etc.
    capacity = models.PositiveIntegerField()

    class Meta:
        ordering = ["name"]

    def __str__(self) -> str:
        return self.name
