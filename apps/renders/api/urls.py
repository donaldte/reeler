from django.urls import path

from apps.renders.api.views import RenderJobDetailViewSet, RenderJobListCreateViewSet

urlpatterns = [
    path(
        "videos/<uuid:video_id>/renders/",
        RenderJobListCreateViewSet.as_view({"get": "list", "post": "create"}),
        name="video-renders",
    ),
    path(
        "render-jobs/<uuid:pk>/",
        RenderJobDetailViewSet.as_view({"get": "retrieve"}),
        name="render-job-detail",
    ),
]
