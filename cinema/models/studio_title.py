from typing import ClassVar

from django.db import models


class StudioTitleQuerySet(models.QuerySet):
    def available(self) -> "StudioTitleQuerySet":
        return self.filter(is_available=True, studio__is_active=True)


class StudioTitle(models.Model):
    """A title a studio will rent us — not a film we have shown.

    Deliberately separate from `Film`. `Film` is the site catalog: every row
    there has a slug, a /movies/<slug> page and a place in the sitemap. This
    table holds ~1,140 Universal titles we have never screened, of which only
    five overlap with `Film`, and it carries exhibition metadata (aspect
    ratio, audio formats, DCP notes) that `Film` has nowhere to put.

    The `film` FK is populated opportunistically for that handful of
    overlaps and is never required.
    """

    # as_manager() returns a Manager that forwards .available() to the
    # queryset, so both StudioTitle.objects.available() and
    # some_queryset.available() work.
    objects: ClassVar[models.Manager["StudioTitle"]] = (
        StudioTitleQuerySet.as_manager()
    )

    studio = models.ForeignKey(
        "cinema.Studio", on_delete=models.CASCADE, related_name="titles"
    )

    # As the studio wrote it ("BAD GUYS 2, THE"). This is the re-import
    # matching key, so it must never be prettified in place.
    original_title = models.CharField(max_length=200)
    # Normalized for display ("The Bad Guys 2").
    title = models.CharField(max_length=200)

    release_date = models.DateField(null=True, blank=True)
    aspect_ratio = models.CharField(max_length=60, blank=True)
    audio = models.CharField(max_length=60, blank=True)
    mpa_rating = models.CharField(max_length=20, blank=True)

    # Parsed for sorting; `runtime_raw` keeps oddities like "119 & 146" so a
    # two-cut title is not silently reduced to one number.
    runtime_minutes = models.PositiveIntegerField(null=True, blank=True)
    runtime_raw = models.CharField(max_length=60, blank=True)

    notes = models.CharField(max_length=200, blank=True)
    variant_note = models.CharField(
        max_length=300,
        blank=True,
        help_text="Other DCP variants collapsed into this row on import.",
    )

    film = models.ForeignKey(
        "cinema.Film",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="studio_titles",
    )

    # Opt-out: everything a studio lists is sponsorable until we say otherwise.
    is_available = models.BooleanField(default=True)
    hidden_reason = models.CharField(max_length=200, blank=True)

    imported_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["title"]
        constraints = [
            models.UniqueConstraint(
                fields=["studio", "original_title", "release_date"],
                name="unique_studio_title_release",
            )
        ]
        indexes = [
            models.Index(fields=["studio", "is_available"]),
            models.Index(fields=["title"]),
        ]

    def __str__(self) -> str:
        return self.title

    @property
    def release_year(self) -> int | None:
        return self.release_date.year if self.release_date else None

    @property
    def format_summary(self) -> str:
        """Exhibition detail folded into one quiet column."""
        parts = [self.aspect_ratio, self.audio, self.notes]
        return " · ".join(part for part in parts if part)
