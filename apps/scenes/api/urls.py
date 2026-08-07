from django.urls import path

from apps.scenes.api.views import SceneListViewSet

urlpatterns = [
    path(
        "videos/<uuid:video_id>/scenes/",
        SceneListViewSet.as_view({"get": "list"}),
        name="video-scenes",
    ),
]
