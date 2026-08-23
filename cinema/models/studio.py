from django.db import models


class Studio(models.Model):
    """A distributor whose availability list we have imported.

    `is_active=False` pulls a studio's whole catalog off the sponsor page in
    one move — when a licensing arrangement lapses or a list goes stale —
    without touching the per-title `is_available` flags underneath it.
    """

    name = models.CharField(max_length=100, unique=True)
    slug = models.SlugField(max_length=100, unique=True)
    is_active = models.BooleanField(default=True)
    catalog_updated = models.DateField(
        null=True,
        blank=True,
        help_text="Revision date printed on the studio's own list.",
    )

    class Meta:
        ordering = ["name"]

    def __str__(self) -> str:
        return self.name
