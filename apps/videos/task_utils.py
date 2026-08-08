"""UploadedVideo-specific wrapper around the generic
`apps.common.task_utils.task_failure_guard` — see that module for the
full rationale (why not `autoretry_for`, etc.).
"""

from collections.abc import Generator
from contextlib import contextmanager

from celery import Task

from apps.common.task_utils import task_failure_guard
from apps.videos.services import fail_pipeline


@contextmanager
def pipeline_task_guard(self: Task, video_id: str, step: str) -> Generator[None]:
    """Wrap a pipeline task's body in this. On any failure it marks the
    video FAILED (via apps.videos.services.fail_pipeline) with a clear
    error_message before re-raising. See
    apps.common.task_utils.task_failure_guard for the full mechanism.

    Usage:
        @shared_task(bind=True, acks_late=True, max_retries=3)
        def some_task(self: Task, video_id: str) -> str:
            update_pipeline_step(video_id, STEP, STEP_RUNNING)
            with pipeline_task_guard(self, video_id, STEP):
                ...  # do the work; raise PermanentPipelineError /
                     # TransientProviderError as appropriate
            return video_id
    """
    with task_failure_guard(
        self,
        label=f"Pipeline step {step!r} for {video_id}",
        on_failure=lambda msg: fail_pipeline(video_id, step, msg),
    ):
        yield
