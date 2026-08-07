import logging
from pathlib import Path
from uuid import UUID

from celery import Task, shared_task
from django.conf import settings
from django.db import transaction

from apps.transcripts.models import Transcript, TranscriptSegment
from apps.videos.constants import PIPELINE_STEP_TRANSCRIPT, STEP_DONE, STEP_RUNNING
from apps.videos.models import UploadedVideo
from apps.videos.services import fail_pipeline, update_pipeline_step
from domain.ai.registry import get_stt_provider
from domain.exceptions import PermanentPipelineError, TransientProviderError

logger = logging.getLogger("reeler")


@shared_task(
    bind=True,
    acks_late=True,
    autoretry_for=(TransientProviderError,),
    retry_backoff=True,
    retry_kwargs={"max_retries": 3},
)
def transcribe_video_task(self: Task, video_id: str) -> str:
    """Runs in parallel with detect_scenes_task (see
    apps/videos/tasks.py::run_analysis_pipeline) — both only need the raw
    upload, not each other's output.
    """
    update_pipeline_step(video_id, PIPELINE_STEP_TRANSCRIPT, STEP_RUNNING)

    video = UploadedVideo.objects.get(id=video_id)
    provider = get_stt_provider(settings)

    try:
        result = provider.transcribe(Path(video.file.path))
    except PermanentPipelineError as exc:
        logger.warning("Transcription failed permanently for %s: %s", video_id, exc)
        fail_pipeline(video_id, PIPELINE_STEP_TRANSCRIPT, str(exc))
        raise

    with transaction.atomic():
        # Idempotent on retry: drop any partial transcript from a prior attempt.
        Transcript.objects.filter(video_id=UUID(video_id)).delete()
        transcript = Transcript.objects.create(
            video_id=video_id,
            language=result.language,
            language_confidence=result.language_confidence,
            full_text=result.full_text,
            provider=result.provider,
            model_name=result.model,
        )
        TranscriptSegment.objects.bulk_create(
            [
                TranscriptSegment(
                    transcript=transcript,
                    index=segment.index,
                    start_time=segment.start,
                    end_time=segment.end,
                    text=segment.text,
                    confidence=segment.confidence,
                )
                for segment in result.segments
            ]
        )

    update_pipeline_step(video_id, PIPELINE_STEP_TRANSCRIPT, STEP_DONE)
    return video_id
