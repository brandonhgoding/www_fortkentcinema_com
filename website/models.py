from django.utils import timezone
from wagtail.models import Page
from wagtail.search import index

from blog.models import BlogAuthor, BlogCategory

from django.db import models
from wagtail.models import Page
from wagtail.fields import RichTextField
from wagtail.admin.panels import FieldPanel
from django.core.paginator import Paginator, EmptyPage, PageNotAnInteger

from cinema.models import TicketRate, Film
from cinema.utils import get_current_or_next_films


class HomePage(Page):
    max_count = 1
    subpage_types = ['website.BlogIndex', 'website.MembershipPage']

    NOW_PLAYING_LIMIT = 2

    def get_context(self, request, *args, **kwargs):
        context = super().get_context(request, *args, **kwargs)
        now = timezone.now()
        context["ticket_rates"] = TicketRate.objects.all()
        context["now_playing"] = get_current_or_next_films(limit=self.NOW_PLAYING_LIMIT, now=now)
        context["upcoming_films"] = Film.objects.filter(
            bookings__booking_start_date__gt=now
        ).order_by("bookings__booking_start_date")[:4]
        return context

class MembershipPage(Page):
    max_count = 1


class BlogIndex(Page):
    """
    A parent page that lists BlogPage children in reverse chronological order.
    """
    intro = RichTextField(blank=True)

    # Only allow BlogPage children
    subpage_types = ['website.BlogPage']

    # # You normally don’t want BlogIndex created under another BlogPage
    # parent_page_types = []  # change as needed

    content_panels = Page.content_panels + [
        FieldPanel("intro"),
    ]

    def get_context(self, request, *args, **kwargs):
        context = super().get_context(request, *args, **kwargs)

        from website.models import BlogPage  # or import at top

        posts = (
            BlogPage.objects
            .child_of(self)
            .live()
            .order_by('-post_date')
        )

        context["object_list"] = posts   # so your old template still works
        return context


class BlogPage(Page):
    subtitle = models.CharField(max_length=200)
    author = models.ForeignKey(BlogAuthor, on_delete=models.RESTRICT)
    category = models.ForeignKey(BlogCategory, on_delete=models.RESTRICT)
    post_date = models.DateField("Post date")
    content = RichTextField()
    header_image = models.ForeignKey(
        'wagtailimages.Image',
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='+'
    )

    search_fields = Page.search_fields + [
        index.SearchField('content'),
        index.FilterField('post_date')
    ]

    content_panels = Page.content_panels + [
        FieldPanel('subtitle'),
        FieldPanel('author'),
        FieldPanel('category'),
        FieldPanel('post_date'),
        FieldPanel('content'),
        FieldPanel('header_image'),
    ]

    parent_page_types = ['website.BlogIndex']
    subpage_types = []

