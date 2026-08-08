from typing import Any, cast

from django.db.models import QuerySet
from django.shortcuts import get_object_or_404
from rest_framework import mixins, status, viewsets
from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response

from apps.accounts.models import User
from apps.renders.api.serializers import RenderJobSerializer
from apps.renders.models import RenderJob
from apps.renders.services import create_render_job
from apps.videos.models import UploadedVideo


class RenderJobListCreateViewSet(
    mixins.ListModelMixin, mixins.CreateModelMixin, viewsets.GenericViewSet
):
    """`GET/POST /api/v1/videos/{video_id}/renders/`."""

    serializer_class = RenderJobSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self) -> QuerySet[RenderJob]:
        user = cast(User, self.request.user)
        return RenderJob.objects.filter(
            video_id=self.kwargs["video_id"], video__project__owner=user
        )

    def create(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        user = cast(User, request.user)
        video = get_object_or_404(UploadedVideo, pk=self.kwargs["video_id"], project__owner=user)
        try:
            render_job = create_render_job(video)
        except ValueError as exc:
            return Response(
                {"error": {"code": "not_ready", "message": str(exc)}},
                status=status.HTTP_400_BAD_REQUEST,
            )
        return Response(self.get_serializer(render_job).data, status=status.HTTP_201_CREATED)


class RenderJobDetailViewSet(mixins.RetrieveModelMixin, viewsets.GenericViewSet):
    """`GET /api/v1/render-jobs/{id}/` — status polling."""

    serializer_class = RenderJobSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self) -> QuerySet[RenderJob]:
        user = cast(User, self.request.user)
        return RenderJob.objects.filter(video__project__owner=user)
