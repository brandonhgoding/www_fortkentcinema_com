from cinema.models import RentalInquiry, SponsorshipInquiry, StudioTitle
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


class RentalInquiryForm(forms.ModelForm):
    """The /rentals/ "Ready to book?" form.

    The sponsor form's twin — same honeypot, same message cap — minus
    anything that needs the film catalog. Only name and email are required:
    the rest is what the owner would ask on the phone anyway, and a lead with
    blanks is still a lead.
    """

    # Honeypot, as on SponsorshipInquiryForm.
    website = forms.CharField(required=False, widget=forms.HiddenInput)

    class Meta:
        model = RentalInquiry
        fields = [
            "contact_name", "email", "phone",
            "preferred_date", "guests", "event_type", "message",
        ]
        labels = {
            "contact_name": "Your name",
            "phone": "Phone (optional)",
            "preferred_date": "Date you have in mind (optional)",
            "event_type": "What's the occasion? (optional)",
        }
        widgets = {
            # A native date picker; Django's DateInput defaults to type="text".
            # The picker only understands ISO dates, hence the format.
            "preferred_date": forms.DateInput(
                attrs={"type": "date"}, format="%Y-%m-%d"
            ),
            "event_type": forms.TextInput(
                attrs={"placeholder": "Birthday, gaming, your own DVD, a film"}
            ),
        }
        # `guests` and `message` are rebuilt in __init__ below, so their
        # labels/widgets live there — see SponsorshipInquiryForm.Meta.

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        # The model's PositiveIntegerField allows 0; a party of nobody is a
        # typo, not a booking. min_value also renders min="1" on the input.
        self.fields["guests"] = forms.IntegerField(
            required=False,
            min_value=1,
            label="How many guests (optional)",
        )
        # Same cap as the sponsor form, for the same reason: an unbounded
        # TextField written by an anonymous POST.
        self.fields["message"] = forms.CharField(
            required=False,
            max_length=2000,
            label="Anything else (optional)",
            widget=forms.Textarea(attrs={"rows": 4}),
            error_messages={
                "max_length": "Please keep this under 2,000 characters.",
            },
        )

    @property
    def is_bot(self) -> bool:
        return bool(self.data.get("website"))
