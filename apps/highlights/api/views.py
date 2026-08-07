from typing import cast

from django.db.models import QuerySet
from rest_framework import mixins, viewsets
from rest_framework.permissions import IsAuthenticated

from apps.accounts.models import User
from apps.highlights.api.serializers import AnalysisResultSerializer
from apps.highlights.models import AnalysisResult


class AnalysisResultViewSet(mixins.RetrieveModelMixin, viewsets.GenericViewSet):
    serializer_class = AnalysisResultSerializer
    permission_classes = [IsAuthenticated]
    lookup_field = "video_id"
    lookup_url_kwarg = "video_id"

    def get_queryset(self) -> QuerySet[AnalysisResult]:
        user = cast(User, self.request.user)
        return AnalysisResult.objects.filter(video__project__owner=user).prefetch_related(
            "highlights"
        )
