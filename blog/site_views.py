from django.views.generic import DetailView, ListView

from .models import BlogPost

RELATED_POST_COUNT = 3


class PostListView(ListView):
    model = BlogPost
    paginate_by = 12
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
        ctx["related_posts"] = self._related_posts(post)
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
