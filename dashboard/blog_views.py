"""Staff surface for the blog: posts, and the authors and categories they file under.

This used to live in /admin/, as three bare model registrations with a
plain-text body field. The dashboard adds what the admin never had: drafts,
a Markdown editor with a live preview, and a draft preview rendered by the
real public template.

Posts are written here on the authors' behalf, so BlogAuthor stays a byline
rather than a login.
"""

import json

from blog.models import BlogAuthor, BlogCategory, BlogPost
from blog.rendering import render_body
from blog.site_views import PostDetailView
from django.contrib import messages
from django.db.models import Count, ProtectedError, Q
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views import View

from .forms import BlogAuthorForm, BlogCategoryForm, BlogPostForm
from .mixins import StaffRequiredMixin

STATUS_FILTERS = [
    ("", "All posts"),
    (BlogPost.Status.DRAFT, "Drafts"),
    (BlogPost.Status.PUBLISHED, "Published"),
]


def _oob(html: str, container_id: str) -> str:
    return html.replace(
        f'<div id="{container_id}">',
        f'<div id="{container_id}" hx-swap-oob="true">',
        1,
    )


def _toast_response(html: str, message: str, kind: str = "success", close: bool = False):
    resp = HttpResponse(html)
    triggers: dict = {"dashboard-toast": {"kind": kind, "message": message}}
    if close:
        triggers["close-drawer"] = True
    resp["HX-Trigger"] = json.dumps(triggers)
    return resp


# --- Posts -------------------------------------------------------------------


def post_list_context(params) -> dict:
    """The filtered post table. `params` is GET or POST, since delete keeps the
    filters the list was showing (the button sends them with hx-include)."""
    q = (params.get("q") or "").strip()
    status = params.get("status") or ""
    category = params.get("category") or ""

    posts = BlogPost.objects.select_related("author", "category")
    if q:
        posts = posts.filter(Q(title__icontains=q) | Q(subtitle__icontains=q))
    if status in BlogPost.Status.values:
        posts = posts.filter(status=status)
    if category:
        posts = posts.filter(category__slug=category)

    return {
        # "draft" sorts before "published", so work in progress leads.
        "posts": posts.order_by("status", "-post_date", "-id"),
        "q": q,
        "selected_status": status,
        "selected_category": category,
    }


def byline_context() -> dict:
    """Both side tables, with the counts that decide whether Delete is offered."""
    return {
        "authors": BlogAuthor.objects.annotate(post_count=Count("blogpost")).order_by(
            "last_name", "first_name"
        ),
        "categories": BlogCategory.objects.annotate(post_count=Count("blogpost")).order_by(
            "name"
        ),
    }


class BlogListView(StaffRequiredMixin, View):
    permission_required = "blog.view_blogpost"

    def get(self, request):
        ctx = post_list_context(request.GET)
        ctx.update(byline_context())
        ctx["statuses"] = STATUS_FILTERS
        ctx["draft_count"] = BlogPost.objects.filter(status=BlogPost.Status.DRAFT).count()
        ctx["published_count"] = BlogPost.objects.published().count()
        return render(request, "dashboard/blog.html", ctx)


def _body_format(form: BlogPostForm) -> str:
    """The format the editor previews in: the post's own, unless staff ticked
    Switch to Markdown on a plain post."""
    if form["use_markdown"].value():
        return BlogPost.BodyFormat.MARKDOWN
    return form.instance.body_format


def _render_editor(request, form: BlogPostForm, post: BlogPost | None):
    return render(
        request,
        "dashboard/blog_editor.html",
        {
            "form": form,
            "post": post,
            "preview_html": render_body(form["content"].value(), _body_format(form)),
        },
    )


def _requested_status(request, current: str) -> str:
    """Which button was pressed. A submit without one (Enter in a text field)
    leaves the status where it was."""
    status = request.POST.get("status")
    return status if status in BlogPost.Status.values else current


SAVE_MESSAGES = {
    # (status before, status after) -> toast
    (BlogPost.Status.DRAFT, BlogPost.Status.DRAFT): "Draft saved",
    (BlogPost.Status.DRAFT, BlogPost.Status.PUBLISHED): "Published",
    (BlogPost.Status.PUBLISHED, BlogPost.Status.PUBLISHED): "Changes saved",
    (BlogPost.Status.PUBLISHED, BlogPost.Status.DRAFT): "Unpublished. The post is a draft again.",
}


def _save_post(request, post: BlogPost | None):
    before = post.status if post else BlogPost.Status.DRAFT
    after = _requested_status(request, before)
    form = BlogPostForm(
        request.POST,
        request.FILES,
        instance=post,
        publishing=after == BlogPost.Status.PUBLISHED,
    )
    if not form.is_valid():
        # is_valid() has already copied the submitted values onto `post`.
        # Reload it so the header (status, "View live" URL) shows what is saved.
        saved = BlogPost.objects.get(pk=post.pk) if post else None
        return _render_editor(request, form, saved)
    if (before, after) == (BlogPost.Status.DRAFT, BlogPost.Status.PUBLISHED) and (
        "post_date" not in form.changed_data
    ):
        # A date changed in this same submit was set on purpose.
        form.instance.date_for_publishing()
    form.instance.status = after
    saved = form.save()
    messages.success(request, SAVE_MESSAGES[(before, after)])
    return redirect("dashboard:blog_post_edit", pk=saved.pk)


class BlogPostCreateView(StaffRequiredMixin, View):
    permission_required = "blog.add_blogpost"

    def get(self, request):
        return _render_editor(request, BlogPostForm(), None)

    def post(self, request):
        return _save_post(request, None)


class BlogPostEditView(StaffRequiredMixin, View):
    permission_required = "blog.change_blogpost"

    def get(self, request, pk):
        post = get_object_or_404(BlogPost, pk=pk)
        return _render_editor(request, BlogPostForm(instance=post), post)

    def post(self, request, pk):
        return _save_post(request, get_object_or_404(BlogPost, pk=pk))


class BlogPostDeleteView(StaffRequiredMixin, View):
    """Delete from the list (swap the table) or from the editor (go to the list)."""

    permission_required = "blog.delete_blogpost"

    def post(self, request, pk):
        post = get_object_or_404(BlogPost, pk=pk)
        title = post.title
        post.delete()
        message = f'Deleted "{title}"'

        if request.headers.get("HX-Target") == "post-list":
            html = render(
                request, "dashboard/_blog_post_list.html", post_list_context(request.POST)
            ).content.decode()
            return _toast_response(html, message)

        messages.success(request, message)
        resp = HttpResponse(status=204)
        resp["HX-Redirect"] = reverse("dashboard:blog")
        return resp


class MarkdownPreviewView(StaffRequiredMixin, View):
    """The editor's live preview. It uses the same renderer as the public page,
    so the preview cannot drift from what gets published.

    A plain-text post sends body_format=plain, plus use_markdown once staff
    tick Switch to Markdown. Anything else previews as Markdown."""

    permission_required = ("blog.add_blogpost", "blog.change_blogpost")

    def has_dashboard_permission(self) -> bool:
        # Either right is enough: the editor serves both new and existing posts.
        return any(self.request.user.has_perm(p) for p in self.permissions_tuple())

    def post(self, request):
        body_format = request.POST.get("body_format")
        if request.POST.get("use_markdown") or body_format != BlogPost.BodyFormat.PLAIN:
            body_format = BlogPost.BodyFormat.MARKDOWN
        return HttpResponse(render_body(request.POST.get("content", ""), body_format))


class BlogPostPreviewView(StaffRequiredMixin, PostDetailView):
    """A post, draft or not, rendered by the real public template.

    Drafts 404 on the public URL, so this is the only way to see one in place.
    The page is marked noindex in its head and header, in case the link
    leaks.
    """

    permission_required = "blog.view_blogpost"

    slug_url_kwarg = None

    def get_queryset(self):
        return BlogPost.objects.select_related("author", "category")

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["preview"] = True
        return ctx

    def render_to_response(self, context, **kwargs):
        resp = super().render_to_response(context, **kwargs)
        resp["X-Robots-Tag"] = "noindex, nofollow"
        return resp


# --- Authors and categories --------------------------------------------------


def _bylines_response(request, toast_message, kind="success", close=True):
    ctx = byline_context()
    html = _oob(
        render(request, "dashboard/_blog_author_list.html", ctx).content.decode(),
        "author-list",
    ) + _oob(
        render(request, "dashboard/_blog_category_list.html", ctx).content.decode(),
        "category-list",
    )
    return _toast_response(html, toast_message, kind=kind, close=close)


def _render_author_form(request, form, action_url, submit_label):
    return render(
        request,
        "dashboard/_blog_author_form.html",
        {
            "form": form,
            "form_action": action_url,
            "submit_label": submit_label,
            "editing": not form.instance._state.adding,
        },
    )


class AuthorCreateView(StaffRequiredMixin, View):
    permission_required = "blog.add_blogauthor"

    def get(self, request):
        return _render_author_form(
            request, BlogAuthorForm(), reverse("dashboard:blog_author_create"), "Create Author"
        )

    def post(self, request):
        form = BlogAuthorForm(request.POST)
        if form.is_valid():
            form.save()
            return _bylines_response(request, "Author created")
        return _render_author_form(
            request, form, reverse("dashboard:blog_author_create"), "Create Author"
        )


class AuthorEditView(StaffRequiredMixin, View):
    permission_required = "blog.change_blogauthor"

    def get(self, request, pk):
        author = get_object_or_404(BlogAuthor, pk=pk)
        return _render_author_form(
            request,
            BlogAuthorForm(instance=author),
            reverse("dashboard:blog_author_edit", args=[pk]),
            "Save Changes",
        )

    def post(self, request, pk):
        author = get_object_or_404(BlogAuthor, pk=pk)
        form = BlogAuthorForm(request.POST, instance=author)
        if form.is_valid():
            form.save()
            return _bylines_response(request, "Author updated")
        return _render_author_form(
            request, form, reverse("dashboard:blog_author_edit", args=[pk]), "Save Changes"
        )


class AuthorDeleteView(StaffRequiredMixin, View):
    permission_required = "blog.delete_blogauthor"

    def post(self, request, pk):
        author = get_object_or_404(BlogAuthor, pk=pk)
        try:
            author.delete()
        except ProtectedError:
            # BlogPost.author is PROTECT. The table hides Delete for an author
            # with posts, so this only fires if one was filed after the page
            # loaded.
            return _bylines_response(
                request,
                f"Can't delete {author}: posts are still filed under them.",
                kind="error",
                close=False,
            )
        return _bylines_response(request, "Author deleted", close=False)


def _render_category_form(request, form, action_url, submit_label):
    return render(
        request,
        "dashboard/_blog_category_form.html",
        {
            "form": form,
            "form_action": action_url,
            "submit_label": submit_label,
            "editing": not form.instance._state.adding,
        },
    )


class CategoryCreateView(StaffRequiredMixin, View):
    permission_required = "blog.add_blogcategory"

    def get(self, request):
        return _render_category_form(
            request, BlogCategoryForm(), reverse("dashboard:blog_category_create"), "Create Category"
        )

    def post(self, request):
        form = BlogCategoryForm(request.POST)
        if form.is_valid():
            form.save()
            return _bylines_response(request, "Category created")
        return _render_category_form(
            request, form, reverse("dashboard:blog_category_create"), "Create Category"
        )


class CategoryEditView(StaffRequiredMixin, View):
    permission_required = "blog.change_blogcategory"

    def get(self, request, pk):
        category = get_object_or_404(BlogCategory, pk=pk)
        return _render_category_form(
            request,
            BlogCategoryForm(instance=category),
            reverse("dashboard:blog_category_edit", args=[pk]),
            "Save Changes",
        )

    def post(self, request, pk):
        category = get_object_or_404(BlogCategory, pk=pk)
        form = BlogCategoryForm(request.POST, instance=category)
        if form.is_valid():
            form.save()
            return _bylines_response(request, "Category updated")
        return _render_category_form(
            request, form, reverse("dashboard:blog_category_edit", args=[pk]), "Save Changes"
        )


class CategoryDeleteView(StaffRequiredMixin, View):
    permission_required = "blog.delete_blogcategory"

    def post(self, request, pk):
        category = get_object_or_404(BlogCategory, pk=pk)
        try:
            category.delete()
        except ProtectedError:
            # BlogPost.category is PROTECT; see AuthorDeleteView.
            return _bylines_response(
                request,
                f'Can\'t delete "{category}": posts are still filed under it.',
                kind="error",
                close=False,
            )
        return _bylines_response(request, "Category deleted", close=False)
