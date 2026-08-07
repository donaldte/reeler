from django.db import models

from apps.common.models import TimeStampedModel
from apps.videos.models import UploadedVideo


class AnalysisResult(TimeStampedModel):
    """One per UploadedVideo — the LLM-generated report (summary, suggested
    title/description/hashtags) plus its ranked Highlight candidates. See
    domain.ai.registry.get_llm_provider / apps/highlights/tasks.py.
    """

    video = models.OneToOneField(
        UploadedVideo, on_delete=models.CASCADE, related_name="analysis_result"
    )
    summary = models.TextField()
    suggested_title = models.CharField(max_length=255)
    suggested_description = models.TextField()
    suggested_hashtags = models.JSONField(default=list, blank=True)
    llm_provider = models.CharField(max_length=64)
    llm_model = models.CharField(max_length=128)
    raw_response = models.JSONField(
        default=dict, blank=True, help_text="Raw provider response, for audit/debugging."
    )

    class Meta:
        db_table = "highlights_analysis_result"

    def __str__(self) -> str:
        return f"AnalysisResult<{self.video_id}>"


class Highlight(TimeStampedModel):
    analysis_result = models.ForeignKey(
        AnalysisResult, on_delete=models.CASCADE, related_name="highlights"
    )
    rank = models.PositiveIntegerField()
    start_time = models.FloatField()
    end_time = models.FloatField()
    rationale = models.TextField()
    score = models.FloatField(null=True, blank=True)
    suggested_clip_title = models.CharField(max_length=255, null=True, blank=True)

    class Meta:
        db_table = "highlights_highlight"
        ordering = ["rank"]

    def __str__(self) -> str:
        return f"Highlight #{self.rank} [{self.start_time:.1f}-{self.end_time:.1f}]"
