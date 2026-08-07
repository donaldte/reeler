from django.db import models

from apps.common.models import TimeStampedModel
from apps.videos.models import UploadedVideo


class Transcript(TimeStampedModel):
    """One per UploadedVideo — the full transcription result from whichever
    SpeechToTextProvider is configured (domain.ai.registry.get_stt_provider).
    """

    video = models.OneToOneField(UploadedVideo, on_delete=models.CASCADE, related_name="transcript")
    language = models.CharField(max_length=16)
    language_confidence = models.FloatField(null=True, blank=True)
    full_text = models.TextField()
    provider = models.CharField(max_length=64)
    model_name = models.CharField(max_length=64)

    class Meta:
        db_table = "transcripts_transcript"

    def __str__(self) -> str:
        return f"Transcript<{self.video_id}, {self.language}>"


class TranscriptSegment(TimeStampedModel):
    transcript = models.ForeignKey(Transcript, on_delete=models.CASCADE, related_name="segments")
    index = models.PositiveIntegerField()
    start_time = models.FloatField()
    end_time = models.FloatField()
    text = models.TextField()
    confidence = models.FloatField(null=True, blank=True)
    # Diarization is not implemented in phase 1 — always NULL. Modeled now so
    # the UI/API/DB shape is already speaker-aware when it lands. See
    # docs/roadmap.md.
    speaker_label = models.CharField(max_length=64, null=True, blank=True)

    class Meta:
        db_table = "transcripts_segment"
        ordering = ["index"]
        constraints = [
            models.UniqueConstraint(
                fields=["transcript", "index"], name="unique_segment_index_per_transcript"
            )
        ]

    def __str__(self) -> str:
        return f"[{self.start_time:.1f}-{self.end_time:.1f}] {self.text[:40]}"
