from blog.models import BlogAuthor, BlogCategory, BlogPost
from django.contrib import admin

# Register your models here.
admin.site.register(BlogAuthor)
admin.site.register(BlogCategory)
admin.site.register(BlogPost)
