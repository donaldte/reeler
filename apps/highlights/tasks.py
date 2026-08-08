import logging
from uuid import UUID

from celery import Task, shared_task
from django.conf import settings
from django.db import transaction

from apps.highlights.models import AnalysisResult, Highlight
from apps.transcripts.models import Transcript
from apps.videos.constants import PIPELINE_STEP_ANALYSIS, STEP_DONE, STEP_RUNNING
from apps.videos.models import UploadedVideo
from apps.videos.services import set_status, update_pipeline_step
from apps.videos.task_utils import pipeline_task_guard
from domain.ai.registry import get_llm_provider
from domain.scene_detection.base import SceneDTO
from domain.transcription.base import TranscriptionResult, TranscriptSegmentDTO

logger = logging.getLogger("reeler")


@shared_task(bind=True, acks_late=True, max_retries=3)
def generate_analysis_task(self: Task, video_id: str) -> str:
    """The chord callback that fires once both transcribe_video_task and
    detect_scenes_task have completed (see
    apps/videos/tasks.py::run_analysis_pipeline). Reads both results back
    from Postgres — Celery's result backend is never used to pass payloads
    between tasks.
    """
    update_pipeline_step(video_id, PIPELINE_STEP_ANALYSIS, STEP_RUNNING)
    set_status(video_id, UploadedVideo.Status.ANALYZING, progress_percent=70)

    with pipeline_task_guard(self, video_id, PIPELINE_STEP_ANALYSIS):
        video = UploadedVideo.objects.select_related("transcript").prefetch_related(
            "transcript__segments", "scenes"
        ).get(id=video_id)  # fmt: skip

        transcript = _to_transcription_result(video.transcript)
        scenes = [
            SceneDTO(index=s.index, start=s.start_time, end=s.end_time) for s in video.scenes.all()
        ]

        provider = get_llm_provider(settings)
        analysis = provider.generate_analysis(
            transcript=transcript, scenes=scenes, video_duration=video.duration_seconds or 0.0
        )

        with transaction.atomic():
            AnalysisResult.objects.filter(video_id=UUID(video_id)).delete()
            result = AnalysisResult.objects.create(
                video_id=video_id,
                summary=analysis.summary,
                suggested_title=analysis.suggested_title,
                suggested_description=analysis.suggested_description,
                suggested_hashtags=analysis.suggested_hashtags,
                llm_provider=analysis.provider,
                llm_model=analysis.model,
                raw_response=analysis.raw_response,
            )
            Highlight.objects.bulk_create(
                [
                    Highlight(
                        analysis_result=result,
                        rank=h.rank,
                        start_time=h.start,
                        end_time=h.end,
                        rationale=h.rationale,
                        score=h.score,
                        suggested_clip_title=h.suggested_clip_title,
                    )
                    for h in analysis.highlights
                ]
            )

        update_pipeline_step(video_id, PIPELINE_STEP_ANALYSIS, STEP_DONE)
        set_status(video_id, UploadedVideo.Status.COMPLETED, progress_percent=100)

    return video_id


def _to_transcription_result(transcript: Transcript) -> TranscriptionResult:
    return TranscriptionResult(
        language=transcript.language,
        language_confidence=transcript.language_confidence,
        full_text=transcript.full_text,
        segments=[
            TranscriptSegmentDTO(
                index=seg.index,
                start=seg.start_time,
                end=seg.end_time,
                text=seg.text,
                confidence=seg.confidence,
            )
            for seg in transcript.segments.all()
        ],
        provider=transcript.provider,
        model=transcript.model_name,
    )
