from blog.models import BlogAuthor, BlogCategory, BlogPost
from django.contrib import admin

admin.site.register(BlogAuthor)
admin.site.register(BlogCategory)


@admin.register(BlogPost)
class BlogPostAdmin(admin.ModelAdmin):
    list_display = ("title", "category", "author", "post_date")
    list_filter = ("category", "author")
    # search_fields is required for FilmAdmin's autocomplete_fields = ("review",).
    search_fields = ("title", "subtitle", "slug")
    ordering = ("-post_date",)
