from cinema.models import SponsorshipInquiry, StudioTitle
from django import forms
from django.urls import reverse_lazy

from .constants import SPONSORSHIP_TIERS


class SponsorshipInquiryForm(forms.ModelForm):
    # Honeypot. A real person leaves this empty; bots fill every field they
    # find. Same trick as the vote page's email capture.
    website = forms.CharField(required=False, widget=forms.HiddenInput)

    class Meta:
        model = SponsorshipInquiry
        fields = [
            "business_name", "contact_name", "email", "phone",
            "tier", "studio_title", "message",
        ]
        labels = {
            "business_name": "Business or organization",
            "contact_name": "Your name",
        }
        # `tier`, `studio_title` and `message` are rebuilt in __init__ below
        # (message to add a max_length with no model migration), so their
        # labels/widgets are set there rather than here — setting them twice
        # would invite the two copies to drift apart.

    def __init__(
        self, *args, defer_film_choices: bool = False, **kwargs
    ) -> None:
        super().__init__(*args, **kwargs)
        self.fields["tier"] = forms.ChoiceField(
            required=False,
            label="What you'd like to cover (optional)",
            choices=[("", "Not sure yet")]
            + [
                (t["key"], f"{t['name']} — from ${t['price']}")
                for t in SPONSORSHIP_TIERS
            ],
        )
        self.fields["studio_title"] = forms.ModelChoiceField(
            required=False,
            label="Film you have in mind (optional)",
            queryset=StudioTitle.objects.available(),
            empty_label="Not sure yet",
        )
        self.fields["phone"].required = False
        # `message` is an unbounded TextField on the model, written by an
        # anonymous POST. Cap it here at the form level (no model migration)
        # so a single request can't stash megabytes in one row.
        self.fields["message"] = forms.CharField(
            required=False,
            max_length=2000,
            widget=forms.Textarea(attrs={"rows": 4}),
            error_messages={
                "max_length": "Please keep this under 2,000 characters.",
            },
        )

        if defer_film_choices:
            self._defer_film_choices()

    def _defer_film_choices(self) -> None:
        """Render the film <select> with only the option that is selected.

        The full list is ~1,140 <option> elements — 56KB, more than half the
        HTML of /sponsor/ — shipped to everyone before anyone opens the
        inquiry drawer. The rest arrive from /sponsor/films the first time a
        reader asks to browse them, and `?films=all` renders them inline for
        anyone without JavaScript.

        Only the *rendering* is trimmed. `queryset` is deliberately left
        alone, so a POST is still validated against every available title and
        a forged or unavailable pk is still rejected.
        """
        field = self.fields["studio_title"]
        choices = [("", field.empty_label)]

        # A bound form (a validation error re-render) carries the pick in
        # `data`; an unbound one carries it in `initial` when the reader
        # arrived on a URL that named a film. Either way the chosen option
        # has to survive, or the select would silently forget it.
        selected = self.data.get("studio_title") or self.initial.get(
            "studio_title"
        )
        if selected:
            chosen = field.queryset.filter(pk=selected).first()
            if chosen is not None:
                choices.append(
                    (chosen.pk, field.label_from_instance(chosen))
                )
        field.widget.choices = choices

        field.widget.attrs.update(
            {
                # innerHTML, not beforeend: the swap has to replace the
                # trimmed list rather than append to it, or the option above
                # would appear twice. after-swap puts the selection back,
                # since replacing the options drops it.
                "hx-get": reverse_lazy("sponsor_films"),
                "hx-trigger": "focus once, sponsor-films-needed once",
                "hx-swap": "innerHTML",
                "hx-target": "this",
                "hx-on::after-swap": (
                    "this.value = this.dataset.selected || ''"
                ),
            }
        )

    @property
    def is_bot(self) -> bool:
        return bool(self.data.get("website"))
