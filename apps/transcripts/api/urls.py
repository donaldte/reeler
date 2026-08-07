from django.urls import path

from apps.transcripts.api.views import TranscriptViewSet

urlpatterns = [
    path(
        "videos/<uuid:video_id>/transcript/",
        TranscriptViewSet.as_view({"get": "retrieve"}),
        name="video-transcript",
    ),
]
