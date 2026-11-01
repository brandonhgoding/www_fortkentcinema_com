import unicodedata

from blog.models import BlogAuthor, BlogCategory, BlogPost
from cinema.models import Engagement
from django import forms
from django.utils import timezone
from django.utils.text import slugify

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


class BlogPostForm(forms.ModelForm):
    """The post editor.

    `status` is not a field here. The editor's buttons decide it (Save draft /
    Publish / Unpublish), and the view sets it on the instance.
    """

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
        if self.instance._state.adding:
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
        return super().save(commit=commit)


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
