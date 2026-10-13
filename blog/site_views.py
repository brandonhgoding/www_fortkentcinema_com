from math import ceil

from django.core.paginator import Page, Paginator
from django.utils.functional import cached_property
from django.views.generic import DetailView, ListView

from .models import BlogPost

RELATED_POST_COUNT = 3


class LeadPage(Page):
    """Page numbering for LeadPaginator: page 1 holds one extra post, so
    every later page starts one further along than per_page alone says."""

    def start_index(self):
        if self.paginator.count == 0:
            return 0
        if self.number == 1:
            return 1
        return self.paginator.per_page * (self.number - 1) + 2

    def end_index(self):
        if self.number == self.paginator.num_pages:
            return self.paginator.count
        return self.paginator.per_page * self.number + 1


class LeadPaginator(Paginator):
    """per_page posts a page, plus one on page 1: the full-width lead card
    over the grid. Later pages are the grid alone, so a full page's rows stay
    complete either way. Orphans are not supported."""

    @cached_property
    def num_pages(self):
        if self.count == 0 and not self.allow_empty_first_page:
            return 0
        rest = max(0, self.count - (self.per_page + 1))
        return 1 + ceil(rest / self.per_page)

    def page(self, number):
        number = self.validate_number(number)
        if number == 1:
            bottom, top = 0, self.per_page + 1
        else:
            bottom = self.per_page * (number - 1) + 1
            top = bottom + self.per_page
        return self._get_page(self.object_list[bottom:top], number, self)

    def _get_page(self, *args, **kwargs):
        return LeadPage(*args, **kwargs)


class PostListView(ListView):
    model = BlogPost
    # Three columns of four rows; page 1 also carries the lead card above
    # them (LeadPaginator).
    paginate_by = 12
    paginator_class = LeadPaginator
    context_object_name = "posts"
    template_name = "blog/post_list.html"

    def get_queryset(self):
        return (
            BlogPost.objects.published()
            .select_related("author", "category")
            .order_by("-post_date", "-id")
        )

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        page_obj, paginator = ctx["page_obj"], ctx["paginator"]
        # Elided range (1 … 4 5 6 … 7) — templates can't call methods with args.
        ctx["page_range"] = paginator.get_elided_page_range(
            page_obj.number, on_each_side=1, on_ends=1
        )
        ctx["ellipsis"] = paginator.ELLIPSIS
        # One query for the page, then split: on page 1 the newest post is the
        # lead card, and everything else is the grid.
        posts = list(page_obj.object_list)
        if page_obj.number == 1 and posts:
            ctx["lead_post"], ctx["grid_posts"] = posts[0], posts[1:]
        else:
            ctx["lead_post"], ctx["grid_posts"] = None, posts
        return ctx


class PostDetailView(DetailView):
    model = BlogPost
    slug_field = "slug"
    slug_url_kwarg = "slug"
    context_object_name = "post"
    template_name = "blog/post_detail.html"

    def get_queryset(self):
        # Drafts 404 here. Staff preview them from the dashboard instead.
        return BlogPost.objects.published().select_related("author", "category")

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        post = ctx["post"]
        ctx["og_image_url"] = (
            self.request.build_absolute_uri(post.header_image.url)
            if post.header_image else None
        )
        related = ctx["related_posts"] = self._related_posts(post)
        # "More from <Category>" only when the block isn't backfilled from
        # other categories.
        ctx["related_all_same_category"] = all(
            p.category_id == post.category_id for p in related
        )
        # Only films with a page to link to. A review can be linked to a film
        # we never booked, and /movies/<slug> 404s for those.
        ctx["reviewed_films"] = post.films.with_page()
        return ctx

    def _related_posts(self, post):
        """Sibling posts to link to: same category first, backfilled with recent
        posts when the category is too thin to fill the block.

        These links are load-bearing. Without them a post has exactly one inbound
        internal link (its listing page), which reads to Google as a page the site
        doesn't consider important — the site's posts sat in "crawled, currently
        not indexed" for precisely that reason.
        """
        siblings = (
            BlogPost.objects.published()
            .select_related("author", "category")
            .exclude(pk=post.pk)
        )

        related = list(
            siblings.filter(category=post.category).order_by("-post_date", "-id")[
                :RELATED_POST_COUNT
            ]
        )

        shortfall = RELATED_POST_COUNT - len(related)
        if shortfall > 0:
            backfill = siblings.exclude(
                pk__in=[p.pk for p in related]
            ).order_by("-post_date", "-id")[:shortfall]
            related.extend(backfill)

        return related
