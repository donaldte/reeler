from django.urls import path

from apps.export_settings.api.views import ExportSettingsViewSet

urlpatterns = [
    path(
        "videos/<uuid:video_id>/settings/",
        ExportSettingsViewSet.as_view({"get": "retrieve", "patch": "partial_update"}),
        name="video-settings",
    ),
]
