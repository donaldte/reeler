import logging
from uuid import UUID

import httpx
from celery import Task, shared_task
from django.conf import settings
from django.core.files.base import ContentFile
from django.db import transaction

from apps.export_settings.models import ExportSettings
from apps.export_settings.services import get_or_create_export_settings
from apps.highlights.models import AnalysisResult, BrollAsset, Highlight
from apps.transcripts.models import Transcript
from apps.videos.constants import PIPELINE_STEP_ANALYSIS, STEP_DONE, STEP_RUNNING
from apps.videos.models import UploadedVideo
from apps.videos.services import set_status, update_pipeline_step
from apps.videos.task_utils import pipeline_task_guard
from domain.ai.base import BrollSuggestionDTO
from domain.ai.registry import get_llm_provider
from domain.scene_detection.base import SceneDTO
from domain.stock_media.registry import get_stock_media_provider
from domain.transcription.base import TranscriptionResult, TranscriptSegmentDTO

logger = logging.getLogger("reeler")

# How long to wait for a single stock-image download. B-roll fetching is
# entirely best-effort (see _fetch_broll_assets) so this just bounds how
# long one slow/stuck download can hold up the analysis task, not a
# correctness requirement.
BROLL_IMAGE_DOWNLOAD_TIMEOUT = 30.0


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
        export_settings = get_or_create_export_settings(video)

        provider = get_llm_provider(settings)
        analysis = provider.generate_analysis(
            transcript=transcript,
            scenes=scenes,
            video_duration=video.duration_seconds or 0.0,
            num_highlights=export_settings.num_highlights,
            temperature=export_settings.temperature,
            export_mode=export_settings.export_mode,
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
                        emoji=h.emoji,
                        transition=h.transition,
                    )
                    for h in analysis.highlights
                ]
            )

        update_pipeline_step(video_id, PIPELINE_STEP_ANALYSIS, STEP_DONE)
        set_status(video_id, UploadedVideo.Status.COMPLETED, progress_percent=100)

        # Best-effort, after the video is already COMPLETED: a B-roll
        # fetch failure (no PEXELS_API_KEY, rate limit, no results) must
        # never turn a successful analysis into a FAILED video, so this
        # never raises -- see _fetch_broll_assets.
        if export_settings.broll_type == ExportSettings.BrollType.STOCK_FOOTAGE:
            _fetch_broll_assets(result, analysis.broll_suggestions)

    return video_id


def _fetch_broll_assets(
    result: AnalysisResult, broll_suggestions: list[BrollSuggestionDTO]
) -> None:
    """Resolves each B-roll suggestion against the configured
    domain.stock_media provider and downloads the top result. Entirely
    best-effort: any failure (missing API key, network error, no search
    results, a bad image response) skips just that one suggestion and is
    logged, never raised -- see the call site's comment for why this must
    never fail the already-COMPLETED video.
    """
    if not broll_suggestions:
        return

    try:
        provider = get_stock_media_provider(settings)
    except ValueError as exc:
        logger.warning("Skipping B-roll fetch for video %s: %s", result.video_id, exc)
        return

    for suggestion in broll_suggestions:
        try:
            results = provider.search_media(query=suggestion.query)
            if not results:
                logger.warning("No stock media results for B-roll query %r", suggestion.query)
                continue
            top = results[0]
            image_response = httpx.get(top.image_url, timeout=BROLL_IMAGE_DOWNLOAD_TIMEOUT)
            image_response.raise_for_status()

            asset = BrollAsset(
                analysis_result=result,
                query=suggestion.query,
                start_time=suggestion.start,
                end_time=suggestion.end,
                source_provider=provider.name,
                source_id=top.id,
            )
            extension = top.image_url.rsplit(".", 1)[-1].split("?")[0][:4] or "jpg"
            asset.image.save(
                f"{top.id}.{extension}", ContentFile(image_response.content), save=False
            )
            asset.save()
        except Exception:
            logger.warning(
                "Skipping B-roll suggestion %r for video %s",
                suggestion.query,
                result.video_id,
                exc_info=True,
            )
            continue


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
