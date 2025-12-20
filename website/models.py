from wagtail.models import Page
from wagtail.search import index

from blog.models import BlogAuthor, BlogCategory

from django.db import models
from wagtail.models import Page
from wagtail.fields import RichTextField
from wagtail.admin.panels import FieldPanel
from django.core.paginator import Paginator, EmptyPage, PageNotAnInteger


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

    def get_context(self, request):
        context = super().get_context(request)
        posts = (
            self.get_children()
            .live()
            .specific()
            .order_by("-first_published_at")
        )

        # Optional pagination (e.g., 10 posts per page)
        paginator = Paginator(posts, 10)
        page = request.GET.get("page")

        try:
            posts = paginator.page(page)
        except PageNotAnInteger:
            posts = paginator.page(1)
        except EmptyPage:
            posts = paginator.page(paginator.num_pages)

        context["posts"] = posts
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

