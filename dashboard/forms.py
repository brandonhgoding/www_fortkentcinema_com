import unicodedata
from typing import cast

from audience.models import (
    Member,
    MembershipBenefit,
    MembershipTerm,
    MembershipTier,
)
from blog.models import BlogAuthor, BlogCategory, BlogPost
from cinema.models import Engagement, Film, Poll, Screen
from django import forms
from django.db.models import Q
from django.utils import timezone
from django.utils.text import slugify

# Labels match the leprinceos SPA (note: "standard" sound shows "Standard",
# not the model's "Standard Surround").
SOUND_SYSTEM_CHOICES = [
    ("standard", "Standard"),
    ("dolby_digital", "Dolby Digital"),
    ("dolby_atmos", "Dolby Atmos"),
]


class ScreenForm(forms.ModelForm):
    sound_system = forms.ChoiceField(
        choices=SOUND_SYSTEM_CHOICES,
        widget=forms.Select(attrs={"class": "input"}),
    )

    class Meta:
        model = Screen
        fields = [
            "name", "capacity", "screen_type", "aspect_ratio",
            "sound_system", "supports_3d",
        ]
        widgets = {
            "name": forms.TextInput(
                attrs={"class": "input", "placeholder": "e.g., Screen 1, Main Auditorium"}
            ),
            "capacity": forms.NumberInput(
                attrs={"class": "input", "min": "1", "placeholder": "e.g., 150"}
            ),
            "screen_type": forms.Select(attrs={"class": "input"}),
            "aspect_ratio": forms.Select(attrs={"class": "input"}),
        }


KIND_OPTIONS = [("REGULAR", "Regular"),
                ("CLASSIC", "Classic"), ("DOUBLE_FEATURE", "Double Feature")]
STATUS_OPTIONS = [("DRAFT", "Draft"), ("CONFIRMED", "Confirmed"), ("CANCELLED", "Cancelled")]


class EngagementForm(forms.ModelForm):
    kind = forms.ChoiceField(choices=KIND_OPTIONS, widget=forms.Select(attrs={"class": "input"}))
    status = forms.ChoiceField(choices=STATUS_OPTIONS, widget=forms.Select(attrs={"class": "input"}))

    class Meta:
        model = Engagement
        fields = ["kind", "display_title", "screen", "start_date", "end_date",
                  "presentation_format", "language", "translation", "status", "show_in_main_listings",
                  "is_free_for_members", "in_ticket_report", "notes"]
        widgets = {
            "display_title": forms.TextInput(attrs={
                "class": "input", "placeholder": "e.g. Creature Double Feature"}),
            "screen": forms.Select(attrs={"class": "input"}),
            "start_date": forms.DateInput(attrs={"class": "input", "type": "date"}, format="%Y-%m-%d"),
            "end_date": forms.DateInput(attrs={"class": "input", "type": "date"}, format="%Y-%m-%d"),
            "presentation_format": forms.Select(attrs={"class": "input"}),
            "language": forms.Select(attrs={"class": "input"}),
            "translation": forms.Select(attrs={"class": "input"}),
            "notes": forms.Textarea(attrs={"class": "textarea", "rows": 3,
                                           "placeholder": "Optional notes about this engagement..."}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["screen"].empty_label = "Select a screen"
        for name in ("start_date", "end_date"):
            self.fields[name].input_formats = ["%Y-%m-%d"]


class PollForm(forms.ModelForm):
    class Meta:
        model = Poll
        fields = ["title", "blurb", "opens_at", "closes_at", "results_visible"]
        widgets = {
            "title": forms.TextInput(attrs={"class": "input"}),
            "blurb": forms.Textarea(attrs={"class": "input", "rows": 3}),
            "opens_at": forms.DateTimeInput(
                attrs={"class": "input", "type": "datetime-local"}
            ),
            "closes_at": forms.DateTimeInput(
                attrs={"class": "input", "type": "datetime-local"}
            ),
        }
        labels = {
            "blurb": "Blurb (shown above the ballot)",
            "results_visible": "Show running tallies while voting is open",
        }


class MemberForm(forms.ModelForm):
    class Meta:
        model = Member
        fields = ["first_name", "last_name", "email", "phone", "notes"]
        widgets = {
            "first_name": forms.TextInput(attrs={"class": "input"}),
            "last_name": forms.TextInput(attrs={"class": "input"}),
            "email": forms.EmailInput(attrs={"class": "input"}),
            # No "optional" placeholder: the drawer label says so.
            "phone": forms.TextInput(attrs={"class": "input"}),
            "notes": forms.Textarea(attrs={"class": "input", "rows": 3}),
        }

    def clean_email(self) -> str:
        # Member.save() lowercases; normalise here too so the uniqueness
        # check catches "ADA@" against a stored "ada@".
        return (self.cleaned_data["email"] or "").strip().lower()


class MembershipTermForm(forms.ModelForm):
    tier = forms.ModelChoiceField(
        queryset=MembershipTier.objects.all(),
        # An explicit, unsubmittable first choice: without it the browser
        # selects the first tier, so a form that prefilled no tier (a blank
        # Add Term, or a renewal of a retired tier) would quietly save
        # whichever tier sorts first.
        empty_label="Choose a tier",
        widget=forms.Select(attrs={"class": "input"}),
    )

    class Meta:
        model = MembershipTerm
        fields = [
            "tier", "started_on", "expires_on",
            "price_paid", "purchased_at", "notes",
        ]
        widgets = {
            "started_on": forms.DateInput(
                attrs={"class": "input", "type": "date"}, format="%Y-%m-%d"
            ),
            "expires_on": forms.DateInput(
                attrs={"class": "input", "type": "date"}, format="%Y-%m-%d"
            ),
            "purchased_at": forms.DateInput(
                attrs={"class": "input", "type": "date"}, format="%Y-%m-%d"
            ),
            "price_paid": forms.NumberInput(
                attrs={"class": "input", "step": "0.01", "min": "0"}
            ),
            "notes": forms.Textarea(attrs={"class": "input", "rows": 2}),
        }

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        # Both are filled from the tier when left blank, so staff can add a
        # renewal by choosing a tier and a start date and nothing else.
        self.fields["expires_on"].required = False
        self.fields["price_paid"].required = False

        # Retired tiers stay selectable on a term that already uses one,
        # so editing an old record cannot quietly re-tier it.
        listed = Q(show_on_membership_page=True)
        if self.instance.pk and self.instance.tier_id:
            listed |= Q(pk=self.instance.tier_id)
        self.fields["tier"].queryset = MembershipTier.objects.filter(listed)
        if self.instance.pk or self.initial.get("tier"):
            cast(forms.ModelChoiceField, self.fields["tier"]).empty_label = None

    def clean(self):
        cleaned = super().clean()
        tier = cleaned.get("tier")
        started_on = cleaned.get("started_on")
        if tier is None:
            return cleaned

        if started_on and not cleaned.get("expires_on"):
            try:
                cleaned["expires_on"] = MembershipTerm.default_expiry(
                    started_on, tier.duration_months
                )
            except OverflowError:
                self.add_error(
                    "expires_on",
                    f"A {tier.duration_months}-month term from this date runs "
                    "past 31 December 9999. Enter an expiry date.",
                )
        if cleaned.get("price_paid") is None:
            cleaned["price_paid"] = tier.price
        # Expiry before start is MembershipTerm.clean()'s to report, so the
        # admin inline refuses it too.
        return cleaned


class MembershipTierForm(forms.ModelForm):
    benefits = forms.ModelMultipleChoiceField(
        queryset=MembershipBenefit.objects.all(),
        required=False,
        widget=forms.CheckboxSelectMultiple,
        help_text="Ticked perks are listed on the membership page, in "
        "benefit sort order.",
    )

    class Meta:
        model = MembershipTier
        fields = [
            "name", "slug", "eyebrow", "price", "duration_months",
            "free_admissions_per_month", "checkout_url", "square_variation_id",
            "benefits",
            "featured", "is_family_tier", "show_on_membership_page",
            "sort_order", "description",
        ]
        widgets = {
            "name": forms.TextInput(attrs={"class": "input"}),
            "slug": forms.TextInput(
                attrs={"class": "input", "placeholder": "e.g. cinema-supporter"}
            ),
            "eyebrow": forms.TextInput(
                attrs={"class": "input", "placeholder": "e.g. Seniors 65+"}
            ),
            "price": forms.NumberInput(
                attrs={"class": "input", "min": "0", "step": "1"}
            ),
            "duration_months": forms.NumberInput(
                attrs={"class": "input", "min": "1", "step": "1"}
            ),
            "free_admissions_per_month": forms.NumberInput(
                attrs={"class": "input", "min": "0", "step": "1"}
            ),
            "checkout_url": forms.URLInput(
                attrs={"class": "input", "placeholder": "https://square.link/..."}
            ),
            "square_variation_id": forms.TextInput(
                attrs={"class": "input", "placeholder": "e.g. LUXWXSDRQGNENE7XDBXPNYXY"}
            ),
            "sort_order": forms.NumberInput(attrs={"class": "input", "step": "1"}),
            "description": forms.Textarea(attrs={"class": "input", "rows": 3}),
        }
        labels = {
            "price": "Price (whole dollars)",
            "duration_months": "Length (months)",
            "free_admissions_per_month": "Free admissions per month",
            "checkout_url": "Square payment link",
            "featured": "Show the 'Best Value' ribbon",
            "is_family_tier": "Show the 'For Families' ribbon",
            "show_on_membership_page": "List on the public membership page",
            "description": "Internal notes (not shown on the website)",
        }

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        # The form field's min_value=0 (from PositiveSmallIntegerField)
        # overwrites the widget's min="1"; the model refuses 0 anyway.
        self.fields["duration_months"].widget.attrs["min"] = "1"
        # The slug is load-bearing outside this database — Square redirects
        # to /thanks?tier=<slug> and the Join button's GA4 tracking carries
        # it — so editing it after creation would break revenue attribution
        # silently, with the page still rendering fine. Same rule the admin
        # enforces (audience/admin.py), for the same reason.
        if self.instance.pk:
            self.fields["slug"].disabled = True
            self.fields["slug"].help_text = (
                "Fixed after creation: Square and GA4 both key off it."
            )

    def clean_slug(self) -> str:
        # A disabled field falls back to the initial value, so an edit can
        # never change it even if the POST carries a different slug.
        return self.instance.slug if self.instance.pk else self.cleaned_data["slug"]


class MembershipBenefitForm(forms.ModelForm):
    class Meta:
        model = MembershipBenefit
        fields = ["name", "description", "sort_order"]
        widgets = {
            "name": forms.TextInput(
                attrs={"class": "input", "placeholder": "e.g. $4 off evening tickets"}
            ),
            "description": forms.Textarea(attrs={"class": "input", "rows": 2}),
            "sort_order": forms.NumberInput(attrs={"class": "input", "step": "1"}),
        }
        labels = {
            "name": "Perk, worded as it should read on the membership page",
            "description": "Internal notes (not shown on the website)",
            "sort_order": "Sort order (variants of the same perk share a value)",
        }


class BlogPostForm(forms.ModelForm):
    """The post editor.

    `status` is not a field here. The editor's buttons decide it (Save draft /
    Publish / Unpublish), and the view sets it on the instance.
    """

    # Reverse of Film.review: which films this post is the review of. Almost
    # always zero or one, but a re-release can share a review with the
    # original, so it is a list.
    films = forms.ModelMultipleChoiceField(
        queryset=Film.objects.all(), required=False
    )
    # A CharField, not the model's SlugField, so "Opening Night!" is
    # slugified by clean_slug rather than rejected.
    slug = forms.CharField(
        required=False, max_length=100, widget=forms.TextInput(attrs={"class": "input"})
    )
    # Only offered on a plain-text (pre-editor) post. body_format itself is
    # not a form field, so saving a plain post keeps it plain.
    use_markdown = forms.BooleanField(required=False, label="Switch to Markdown")

    class Meta:
        model = BlogPost
        fields = [
            "title", "subtitle", "slug", "author", "category", "post_date",
            "header_image", "content",
        ]
        widgets = {
            "title": forms.TextInput(attrs={"class": "input"}),
            "subtitle": forms.TextInput(attrs={"class": "input"}),
            "author": forms.Select(attrs={"class": "input"}),
            "category": forms.Select(attrs={"class": "input"}),
            "post_date": forms.DateInput(
                attrs={"class": "input", "type": "date"}, format="%Y-%m-%d"
            ),
            "header_image": forms.ClearableFileInput(attrs={"accept": "image/*"}),
            "content": forms.Textarea(attrs={"class": "input markdownInput", "rows": 24}),
        }
        labels = {
            "slug": "URL",
            "post_date": "Post date",
            "content": "Body",
        }

    def __init__(self, *args, publishing: bool = False, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        # A draft can be saved before the body is written. A post can't be
        # published without one.
        self.fields["content"].required = publishing
        self.fields["author"].empty_label = "Select an author"
        self.fields["category"].empty_label = "Select a category"
        self.fields["post_date"].input_formats = ["%Y-%m-%d"]
        # Not `instance.pk`: the UUID default fills that in before the first save.
        if not self.instance._state.adding:
            self.initial.setdefault("films", list(self.instance.films.all()))
        else:
            self.initial.setdefault("post_date", timezone.localdate())

    def clean_slug(self) -> str:
        return slugify(self.cleaned_data.get("slug") or "")

    def clean(self):
        cleaned = super().clean()
        # A blank URL is filled from the subtitle by SlugModelMixin's own
        # rule. Doing it here rather than in save() lets ModelForm's unique
        # check run on the result, so a clash shows up as a field error
        # instead of an IntegrityError.
        if not cleaned.get("slug") and cleaned.get("subtitle"):
            cleaned["slug"] = self.instance.generate_slug(cleaned["subtitle"])
        return cleaned

    def save(self, commit: bool = True) -> BlogPost:
        if self.cleaned_data.get("use_markdown"):
            self.instance.body_format = BlogPost.BodyFormat.MARKDOWN
        post = super().save(commit=commit)
        if commit:
            self._save_films(post)
        return post

    def _save_films(self, post: BlogPost) -> None:
        chosen = set(f.pk for f in self.cleaned_data.get("films") or [])
        post.films.exclude(pk__in=chosen).update(review=None)
        Film.objects.filter(pk__in=chosen).update(review=post)


def _normalized_name(text: str) -> str:
    """A name compared for duplicates: case, Unicode form and runs of
    whitespace don't count."""
    return " ".join(unicodedata.normalize("NFKC", text).casefold().split())


class _SlugOnCreateMixin:
    """Author and category slugs are set from the name on first save and never
    change after that. A duplicate name would therefore fail on the unique
    slug. This check catches it first, while it can still be reported.

    Names are compared as names, not only as slugs. A name with no ASCII
    letters or digits ('★★★') gets a fallback slug made unique (author,
    author-2), so a slug check alone let the same name in twice. The slug
    check stays for names that differ but slugify alike ('Café', 'Cafe').
    """

    duplicate_message = "That name is already taken."

    def clean(self):
        cleaned = super().clean()
        if self.errors:
            return cleaned
        model = self._meta.model
        candidate = model(**cleaned)
        # Authors and categories number in the dozens, so comparing in
        # Python is cheaper than teaching the database the same rule.
        # Renames are checked too: the slug stays put, but two rows that
        # read the same would be indistinguishable in the editor.
        name = _normalized_name(getattr(candidate, model.slug_field))
        others = model.objects.exclude(pk=self.instance.pk)
        if any(_normalized_name(getattr(other, model.slug_field)) == name
               for other in others):
            raise forms.ValidationError(self.duplicate_message)
        if self.instance._state.adding and model.objects.filter(
            slug=candidate.generate_slug()
        ).exists():
            raise forms.ValidationError(self.duplicate_message)
        return cleaned


class BlogAuthorForm(_SlugOnCreateMixin, forms.ModelForm):
    duplicate_message = "There is already an author with that name."

    class Meta:
        model = BlogAuthor
        fields = ["first_name", "last_name"]
        widgets = {
            "first_name": forms.TextInput(attrs={"class": "input"}),
            "last_name": forms.TextInput(attrs={"class": "input"}),
        }


class BlogCategoryForm(_SlugOnCreateMixin, forms.ModelForm):
    duplicate_message = "There is already a category with that name."

    class Meta:
        model = BlogCategory
        fields = ["name"]
        widgets = {"name": forms.TextInput(attrs={"class": "input"})}
