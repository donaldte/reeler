from rest_framework.routers import DefaultRouter

from apps.videos.api.views import UploadedVideoViewSet

router = DefaultRouter()
router.register("videos", UploadedVideoViewSet, basename="video")

urlpatterns = router.urls
