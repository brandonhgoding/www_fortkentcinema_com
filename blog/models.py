import uuid

from django.db import models
from django.urls import reverse

from website.mixins import SlugModelMixin


# Create your models here.
class BlogAuthor(SlugModelMixin):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    first_name = models.CharField(max_length=100)
    last_name = models.CharField(max_length=100)

    slug_field = "full_name"

    @property
    def full_name(self) -> str:
        return f"{self.first_name} {self.last_name}"

    def __str__(self) -> str:
        return f"{self.first_name} {self.last_name}"


class BlogCategory(SlugModelMixin):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=100)

    slug_field = "name"

    def __str__(self) -> str:
        return self.name


class BlogPost(SlugModelMixin):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    title = models.CharField(max_length=200)
    subtitle = models.CharField(max_length=200)
    author = models.ForeignKey(BlogAuthor, on_delete=models.CASCADE)
    category = models.ForeignKey(BlogCategory, on_delete=models.CASCADE)
    post_date = models.DateField()
    content = models.TextField()
    summary = models.TextField(blank=True, null=True)
    header_image = models.ImageField(upload_to="blog/images/", null=True, blank=True)

    slug_field = "subtitle"

    class Meta:
        ordering = ["-post_date"]

    def __str__(self) -> str:
        return self.subtitle

    def get_absolute_url(self):
        return reverse("website:blog_detail", kwargs={"slug": self.slug})
