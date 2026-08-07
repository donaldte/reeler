from django.urls import path

from apps.highlights.api.views import AnalysisResultViewSet

urlpatterns = [
    path(
        "videos/<uuid:video_id>/analysis/",
        AnalysisResultViewSet.as_view({"get": "retrieve"}),
        name="video-analysis",
    ),
]
