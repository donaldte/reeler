from typing import Any, cast

from django.db.models import QuerySet
from rest_framework import mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.serializers import BaseSerializer

from apps.accounts.models import User
from apps.videos.api.serializers import UploadedVideoSerializer, VideoUploadSerializer
from apps.videos.models import UploadedVideo
from apps.videos.services import create_video_and_launch_pipeline, status_payload


class UploadedVideoViewSet(
    mixins.CreateModelMixin,
    mixins.RetrieveModelMixin,
    mixins.ListModelMixin,
    viewsets.GenericViewSet,
):
    """`POST /api/v1/videos/` uploads a video and launches the analysis
    pipeline; `GET /api/v1/videos/{id}/status/` polls its progress.
    """

    serializer_class = UploadedVideoSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self) -> QuerySet[UploadedVideo]:
        user = cast(User, self.request.user)
        return UploadedVideo.objects.filter(project__owner=user).select_related("project")

    def get_serializer_class(self) -> type[BaseSerializer]:
        if self.action == "create":
            return VideoUploadSerializer
        return UploadedVideoSerializer

    def create(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        upload_serializer = VideoUploadSerializer(data=request.data)
        upload_serializer.is_valid(raise_exception=True)
        video = create_video_and_launch_pipeline(
            owner=cast(User, request.user),
            uploaded_file=upload_serializer.validated_data["file"],
        )
        return Response(UploadedVideoSerializer(video).data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=["get"])
    def status(self, request: Request, pk: str | None = None) -> Response:
        video = self.get_object()
        return Response(status_payload(video))
