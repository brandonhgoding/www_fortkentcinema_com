from django.views.generic import DetailView, ListView

from .models import BlogPost


class PostListView(ListView):
    model = BlogPost
    paginate_by = 6
    context_object_name = "posts"
    template_name = "blog/post_list.html"

    def get_queryset(self):
        return BlogPost.objects.select_related("author", "category").order_by("-post_date", "-id")

    def get_template_names(self):
        if self.request.headers.get("HX-Request"):
            return ["blog/_post_cards.html"]
        return [self.template_name]

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        # Template can't do request.headers.HX-Request (hyphen); expose a flag.
        ctx["is_htmx"] = bool(self.request.headers.get("HX-Request"))
        return ctx


class PostDetailView(DetailView):
    model = BlogPost
    slug_field = "slug"
    slug_url_kwarg = "slug"
    context_object_name = "post"
    template_name = "blog/post_detail.html"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        post = ctx["post"]
        ctx["og_image_url"] = (
            self.request.build_absolute_uri(post.header_image.url)
            if post.header_image else None
        )
        return ctx
