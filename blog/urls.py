from rest_framework.routers import DefaultRouter

from .views import BlogAuthorViewSet, BlogCategoryViewSet, BlogPostViewSet

router = DefaultRouter()
router.register(r"posts", BlogPostViewSet, basename="post")
router.register(r"authors", BlogAuthorViewSet, basename="author")
router.register(r"categories", BlogCategoryViewSet, basename="category")

urlpatterns = router.urls
