from typing import cast

from django.db.models import QuerySet
from rest_framework import mixins, viewsets
from rest_framework.permissions import IsAuthenticated

from apps.accounts.models import User
from apps.transcripts.api.serializers import TranscriptSerializer
from apps.transcripts.models import Transcript


class TranscriptViewSet(mixins.RetrieveModelMixin, viewsets.GenericViewSet):
    serializer_class = TranscriptSerializer
    permission_classes = [IsAuthenticated]
    lookup_field = "video_id"
    lookup_url_kwarg = "video_id"

    def get_queryset(self) -> QuerySet[Transcript]:
        user = cast(User, self.request.user)
        return Transcript.objects.filter(video__project__owner=user).prefetch_related("segments")
