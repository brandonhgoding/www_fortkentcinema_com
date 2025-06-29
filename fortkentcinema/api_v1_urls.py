from django.urls import include, path

import blog.urls as blog_urls
from cinema.urls import film_urlpatterns

urlpatterns = [
    path("blog/", include(blog_urls)),
    path("films/", include(film_urlpatterns)),
]
