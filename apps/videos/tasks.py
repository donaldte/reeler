import logging
from pathlib import Path

from celery import Task, chain, chord, group, shared_task

from apps.videos.constants import PIPELINE_STEP_METADATA, STEP_DONE, STEP_RUNNING
from apps.videos.models import UploadedVideo
from apps.videos.services import set_status, update_pipeline_step
from apps.videos.task_utils import pipeline_task_guard
from domain.media.ffprobe import probe

logger = logging.getLogger("reeler")


@shared_task(bind=True, acks_late=True, max_retries=3)
def extract_metadata_task(self: Task, video_id: str) -> str:
    """First pipeline step: run ffprobe and populate UploadedVideo's media
    fields. Naturally idempotent — simply overwrites the fields on retry.
    """
    update_pipeline_step(video_id, PIPELINE_STEP_METADATA, STEP_RUNNING)
    set_status(video_id, UploadedVideo.Status.EXTRACTING_METADATA, progress_percent=5)

    with pipeline_task_guard(self, video_id, PIPELINE_STEP_METADATA):
        video = UploadedVideo.objects.get(id=video_id)
        metadata = probe(Path(video.file.path))

        video.duration_seconds = metadata.duration_seconds
        video.width = metadata.width
        video.height = metadata.height
        video.fps = metadata.fps
        video.has_audio = metadata.has_audio
        video.video_codec = metadata.video_codec
        video.audio_codec = metadata.audio_codec or ""
        video.file_size_bytes = metadata.file_size_bytes
        video.save(
            update_fields=[
                "duration_seconds", "width", "height", "fps", "has_audio",
                "video_codec", "audio_codec", "file_size_bytes", "updated_at",
            ]
        )  # fmt: skip

        update_pipeline_step(video_id, PIPELINE_STEP_METADATA, STEP_DONE)
        set_status(
            video_id, UploadedVideo.Status.TRANSCRIBING_AND_DETECTING_SCENES, progress_percent=15
        )

    return video_id


def run_analysis_pipeline(video_id: str) -> None:
    """Builds and dispatches the full analysis task graph for one video.

    Transcription and scene detection only need the raw upload (not each
    other's output), so they run in parallel via `group`; the `chord`
    callback only fires once both finish, then reads both results back from
    Postgres to produce the final LLM analysis.
    """
    # Imported here rather than at module load time: those apps' tasks.py
    # import back from apps.videos.services, and importing them eagerly at
    # module scope would risk a circular import during Django app loading.
    from apps.highlights.tasks import generate_analysis_task
    from apps.scenes.tasks import detect_scenes_task
    from apps.transcripts.tasks import transcribe_video_task

    workflow = chain(
        extract_metadata_task.si(video_id),
        chord(
            group(transcribe_video_task.si(video_id), detect_scenes_task.si(video_id)),
            generate_analysis_task.si(video_id),
        ),
    )
    workflow.apply_async()
