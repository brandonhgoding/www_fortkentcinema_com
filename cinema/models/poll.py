from typing import Any, ClassVar

from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import Manager, Q
from django.urls import reverse
from django.utils import timezone
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

    # The voting window, enforced on top of status: an OPEN poll takes votes
    # only between these (blank means no limit on that side). Staff still
    # move it to CLOSED by hand to record the round as decided.
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

    def clean(self) -> None:
        if self.opens_at and self.closes_at and self.closes_at <= self.opens_at:
            raise ValidationError({"closes_at": "Closes must be after Opens."})

    @staticmethod
    def started_q(now) -> Q:
        return Q(opens_at__isnull=True) | Q(opens_at__lte=now)

    @staticmethod
    def ended_q(now) -> Q:
        return Q(closes_at__isnull=False, closes_at__lte=now)

    def has_started(self, now=None) -> bool:
        now = now or timezone.now()
        return self.opens_at is None or self.opens_at <= now

    def has_ended(self, now=None) -> bool:
        now = now or timezone.now()
        return self.closes_at is not None and self.closes_at <= now

    def is_accepting_votes(self, now=None) -> bool:
        now = now or timezone.now()
        return (
            self.status == PollStatus.OPEN
            and self.has_started(now)
            and not self.has_ended(now)
        )

    @property
    def total_votes(self) -> int:
        return self.votes.count()

    def contact_counts(self) -> dict[str, int]:
        """How many voters chose each email preference. Votes cast before
        the ballot asked for an address are left out."""
        counts = {key: 0 for key in EmailPreference.values}
        rows = (
            self.votes.exclude(email="")
            .values("email_preference")
            .annotate(n=models.Count("id"))
        )
        for row in rows:
            counts[row["email_preference"]] = row["n"]
        return counts

    def contactable_votes(self):
        """Votes whose address we may write to, oldest first."""
        return (
            self.votes.exclude(email="")
            .exclude(email_preference=EmailPreference.NONE)
            .order_by("created_at")
        )

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


class EmailPreference(models.TextChoices):
    """What a voter asked us to do with the address they gave."""

    RESULTS = "RESULTS", "Tell me the results, but don't add me to the mailing list"
    SUBSCRIBE = "SUBSCRIBE", "Add me to the mailing list"
    NONE = "NONE", "Don't email me"


class Vote(models.Model):
    """A single ballot cast.

    `voter_key` is a random token from a long-lived cookie. `email` is
    required on the public ballot (one vote per address per round, enforced
    below) and `email_preference` is the voter's own say in what we do with
    it; see EmailPreference. Blank email and NONE only on votes cast before
    the address was asked for.
    """

    objects: ClassVar[Manager["Vote"]]

    EMAIL_MAX_LENGTH: ClassVar[int] = 254

    poll = models.ForeignKey(Poll, on_delete=models.CASCADE, related_name="votes")
    option = models.ForeignKey(
        PollOption, on_delete=models.CASCADE, related_name="votes"
    )
    voter_key = models.CharField(max_length=36, db_index=True)
    email = models.EmailField(max_length=EMAIL_MAX_LENGTH, blank=True, default="")
    email_preference = models.CharField(
        max_length=20,
        choices=EmailPreference.choices,
        default=EmailPreference.NONE,
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["poll", "voter_key"], name="cinema_vote_one_per_poll_per_voter"
            ),
            models.UniqueConstraint(
                fields=["poll", "email"],
                condition=~models.Q(email=""),
                name="cinema_vote_one_per_poll_per_email",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.voter_key[:8]}… → {self.option.film.title}"

    def save(self, *args: Any, **kwargs: Any) -> None:
        # Lowercased so the per-address constraint cannot be sidestepped by
        # capitalisation. Same rule as Subscriber.
        self.email = (self.email or "").strip().lower()
        super().save(*args, **kwargs)

    @property
    def wants_email(self) -> bool:
        return bool(self.email) and self.email_preference != EmailPreference.NONE
