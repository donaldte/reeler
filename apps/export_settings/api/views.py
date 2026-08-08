from typing import Any, cast

from django.db.models import QuerySet
from django.shortcuts import get_object_or_404
from rest_framework import viewsets
from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response

from apps.accounts.models import User
from apps.export_settings.api.serializers import ExportSettingsSerializer
from apps.export_settings.models import ExportSettings
from apps.export_settings.services import get_or_create_export_settings, maybe_rerun_analysis
from apps.videos.models import UploadedVideo


class ExportSettingsViewSet(viewsets.GenericViewSet):
    """`GET/PATCH /api/v1/videos/{video_id}/settings/`.

    Not a standard single-object lookup (ExportSettings is FK, not O2O, to
    UploadedVideo — see the model docstring) so this uses custom
    retrieve/partial_update actions rather than DRF's generic mixins,
    always resolving to "the latest row, or a default-valued one created
    on first touch" via get_or_create_export_settings.
    """

    serializer_class = ExportSettingsSerializer
    permission_classes = [IsAuthenticated]

    def _get_video(self) -> UploadedVideo:
        user = cast(User, self.request.user)
        return get_object_or_404(UploadedVideo, pk=self.kwargs["video_id"], project__owner=user)

    def retrieve(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        settings_obj = get_or_create_export_settings(self._get_video())
        return Response(self.get_serializer(settings_obj).data)

    def partial_update(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        video = self._get_video()
        settings_obj = get_or_create_export_settings(video)

        serializer = self.get_serializer(settings_obj, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)

        changed_fields = {
            field
            for field, value in serializer.validated_data.items()
            if getattr(settings_obj, field) != value
        }
        serializer.save()
        did_rerun = maybe_rerun_analysis(video, changed_fields)

        data: dict[str, Any] = dict(serializer.data)
        data["rerun_triggered"] = did_rerun
        return Response(data)

    def get_queryset(self) -> QuerySet[ExportSettings]:
        # required by GenericViewSet; retrieve/partial_update above don't use
        # it (they resolve through get_or_create_export_settings instead).
        return ExportSettings.objects.none()
