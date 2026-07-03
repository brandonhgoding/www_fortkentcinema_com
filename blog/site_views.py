from django.views.generic import ListView

from .models import BlogPost


class PostListView(ListView):
    model = BlogPost
    paginate_by = 6
    context_object_name = "posts"
    template_name = "blog/post_list.html"

    def get_template_names(self):
        if self.request.headers.get("HX-Request"):
            return ["blog/_post_cards.html"]
        return [self.template_name]

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        # Template can't do request.headers.HX-Request (hyphen); expose a flag.
        ctx["is_htmx"] = bool(self.request.headers.get("HX-Request"))
        return ctx
