from typing import Any, ClassVar

from django.db import models
from django.db.models import Manager
from django.urls import reverse
from django.utils.text import slugify

from .engagement import Engagement
from .film import Film


class PollStatus(models.TextChoices):
    DRAFT = "DRAFT", "Draft"
    OPEN = "OPEN", "Open"
    CLOSED = "CLOSED", "Closed"
    ANNOUNCED = "ANNOUNCED", "Announced"


class Poll(models.Model):
    """One round of audience voting on what we screen next.

    The ballot is curated: staff pick every option. That is what makes a
    stuffed ballot survivable — the winner is always a film we already
    approved for screening.
    """

    objects: ClassVar[Manager["Poll"]]

    title = models.CharField(max_length=200)
    slug = models.SlugField(max_length=200, unique=True, blank=True)
    blurb = models.TextField(
        blank=True, help_text="Shown above the ballot. One or two sentences."
    )

    opens_at = models.DateTimeField(null=True, blank=True)
    closes_at = models.DateTimeField(null=True, blank=True)

    status = models.CharField(
        max_length=20, choices=PollStatus.choices, default=PollStatus.DRAFT
    )
    results_visible = models.BooleanField(
        default=True,
        help_text="Show running tallies while voting is open. Off hides them "
        "until the round closes.",
    )

    winner = models.ForeignKey(
        "cinema.PollOption",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="won_polls",
    )
    # The booking the winner became. This is what turns the results page from
    # "Casablanca won" into "Casablanca won, here are the showtimes".
    engagement = models.ForeignKey(
        Engagement,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="polls",
    )

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        constraints = [
            # The public page assumes a single live poll. Enforced in the
            # database so a dashboard bug cannot produce two.
            models.UniqueConstraint(
                fields=["status"],
                condition=models.Q(status="OPEN"),
                name="cinema_poll_only_one_open",
            )
        ]
        verbose_name = "Poll"
        verbose_name_plural = "Polls"

    def __str__(self) -> str:
        return self.title

    def get_absolute_url(self) -> str:
        return reverse("vote_archive", kwargs={"slug": self.slug})

    def generate_slug(self) -> str:
        base = slugify(self.title) or "poll"
        slug = base
        n = 2
        while Poll.objects.filter(slug=slug).exclude(pk=self.pk).exists():
            slug = f"{base}-{n}"
            n += 1
        return slug

    def save(self, *args: Any, **kwargs: Any) -> None:
        if not self.slug:
            self.slug = self.generate_slug()
        super().save(*args, **kwargs)

    @property
    def total_votes(self) -> int:
        return self.votes.count()

    def tallies(self, by_rank: bool = False) -> list[dict]:
        """Per-option counts and whole-number percentages.

        Ballot order by default; `by_rank=True` sorts by descending count,
        which is what the results view and the announce step want.
        """
        total = self.total_votes
        rows = []
        for option in self.options.select_related("film").annotate(
            n=models.Count("votes")
        ):
            rows.append(
                {
                    "option": option,
                    "count": option.n,
                    "percent": round(option.n / total * 100) if total else 0,
                }
            )
        if by_rank:
            rows.sort(key=lambda r: r["count"], reverse=True)
        return rows


class PollOption(models.Model):
    """One film on a ballot.

    Points at a real `Film`, so a ballot reuses posters, runtimes and TMDB
    metadata we already have — building a round is picking films, not typing
    metadata.
    """

    objects: ClassVar[Manager["PollOption"]]

    poll = models.ForeignKey(Poll, on_delete=models.CASCADE, related_name="options")
    film = models.ForeignKey(
        Film, on_delete=models.PROTECT, related_name="poll_options"
    )
    blurb = models.CharField(
        max_length=280,
        blank=True,
        help_text="Optional pitch for this film. Falls back to the synopsis.",
    )
    sort_order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["sort_order", "id"]
        constraints = [
            models.UniqueConstraint(
                fields=["poll", "film"], name="cinema_polloption_unique_film_per_poll"
            )
        ]

    def __str__(self) -> str:
        return f"{self.film.title} ({self.poll.title})"

    @property
    def description(self) -> str:
        return self.blurb or self.film.description


class Vote(models.Model):
    """A single ballot cast.

    `voter_key` is a random token from a long-lived cookie. `ip_hash` is a
    salted hash — never the raw address — kept only so a flood from one
    connection is visible and cappable.
    """

    objects: ClassVar[Manager["Vote"]]

    poll = models.ForeignKey(Poll, on_delete=models.CASCADE, related_name="votes")
    option = models.ForeignKey(
        PollOption, on_delete=models.CASCADE, related_name="votes"
    )
    voter_key = models.CharField(max_length=36, db_index=True)
    ip_hash = models.CharField(max_length=64, blank=True, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["poll", "voter_key"], name="cinema_vote_one_per_poll_per_voter"
            )
        ]

    def __str__(self) -> str:
        return f"{self.voter_key[:8]}… → {self.option.film.title}"
