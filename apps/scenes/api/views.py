from typing import cast

from django.db.models import QuerySet
from rest_framework import mixins, viewsets
from rest_framework.permissions import IsAuthenticated

from apps.accounts.models import User
from apps.scenes.api.serializers import SceneSerializer
from apps.scenes.models import Scene


class SceneListViewSet(mixins.ListModelMixin, viewsets.GenericViewSet):
    serializer_class = SceneSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self) -> QuerySet[Scene]:
        user = cast(User, self.request.user)
        return Scene.objects.filter(video_id=self.kwargs["video_id"], video__project__owner=user)
