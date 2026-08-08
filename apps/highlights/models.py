from django.db import models

from apps.common.models import TimeStampedModel
from apps.videos.models import UploadedVideo


def upload_broll_path(instance: "BrollAsset", filename: str) -> str:
    return f"broll/{instance.analysis_result_id}/{instance.id}/{filename}"


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
    emoji = models.CharField(max_length=8, null=True, blank=True)
    transition = models.CharField(
        max_length=8,
        null=True,
        blank=True,
        help_text="AI-suggested per-clip transition ('cut' or 'fade'); refines, does "
        "not override, ExportSettings.transition_style. See domain/rendering/renderer.py.",
    )

    class Meta:
        db_table = "highlights_highlight"
        ordering = ["rank"]

    def __str__(self) -> str:
        return f"Highlight #{self.rank} [{self.start_time:.1f}-{self.end_time:.1f}]"


class BrollAsset(TimeStampedModel):
    """A stock-photo B-roll suggestion from the same LLM analysis call that
    produces `Highlight` rows, resolved against a `domain.stock_media`
    provider and downloaded. A second child of `AnalysisResult` rather
    than a new app — same parent, same populating task
    (`apps/highlights/tasks.py::generate_analysis_task`).

    `image` is nullable/blank because fetching is best-effort: a Pexels
    failure (no API key, rate limit, no results) skips that one
    suggestion rather than failing analysis — see
    `apps/highlights/tasks.py::_fetch_broll_assets`. A row with no image
    is simply never used by the renderer.
    """

    analysis_result = models.ForeignKey(
        AnalysisResult, on_delete=models.CASCADE, related_name="broll_assets"
    )
    query = models.CharField(max_length=255)
    start_time = models.FloatField()
    end_time = models.FloatField()
    image = models.ImageField(upload_to=upload_broll_path, null=True, blank=True)
    source_provider = models.CharField(max_length=32, blank=True, default="")
    source_id = models.CharField(max_length=64, blank=True, default="")

    class Meta:
        db_table = "highlights_broll_asset"
        ordering = ["start_time"]

    def __str__(self) -> str:
        return f"BrollAsset[{self.start_time:.1f}-{self.end_time:.1f}] {self.query!r}"

    @property
    def image_path(self) -> str | None:
        """A plain string, not a Django FieldFile — what lets this model
        satisfy domain.rendering.broll.BrollAssetLike structurally without
        that framework-free module ever importing/touching a FieldFile.
        """
        return self.image.path if self.image else None
