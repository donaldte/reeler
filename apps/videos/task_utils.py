"""Shared failure-handling for every pipeline task.

`@shared_task(..., autoretry_for=(TransientProviderError,))` looks
appealing but has a sharp edge: Celery implements it by wrapping the whole
task call *outside* the function body, so when retries are finally
exhausted, the re-raised exception happens in code the task function has
already exited — nothing inside the function (however broad the
try/except) ever sees it. The practical symptom: a video gets stuck
showing "Analyzing 70%" forever, no error, no way to know it failed.

`pipeline_task_guard` fixes this by doing retries manually (`self.retry()`
called from *inside* the guarded block, so we control exactly what happens
when retries run out) and by adding a last-resort `except Exception` so
literally any failure — a permanent error, a transient one that ran out of
retries, a Celery soft-time-limit, a bug — always marks the video FAILED
with a message, never silently stuck. See docs/ai_pipeline.md.
"""

import logging
from collections.abc import Generator
from contextlib import contextmanager

from celery import Task

from apps.videos.services import fail_pipeline
from domain.exceptions import PermanentPipelineError, TransientProviderError

logger = logging.getLogger("reeler")

RETRY_BASE_DELAY_SECONDS = 60
RETRY_MAX_DELAY_SECONDS = 900


@contextmanager
def pipeline_task_guard(self: Task, video_id: str, step: str) -> Generator[None]:
    """Wrap a pipeline task's body in this. On any failure it marks the
    video FAILED (via apps.videos.services.fail_pipeline) with a clear
    error_message before re-raising, except for a TransientProviderError
    that still has retries left — that one triggers `self.retry()` instead.

    Usage:
        @shared_task(bind=True, acks_late=True, max_retries=3)
        def some_task(self: Task, video_id: str) -> str:
            update_pipeline_step(video_id, STEP, STEP_RUNNING)
            with pipeline_task_guard(self, video_id, STEP):
                ...  # do the work; raise PermanentPipelineError /
                     # TransientProviderError as appropriate
            return video_id
    """
    try:
        yield
    except PermanentPipelineError as exc:
        logger.warning("Pipeline step %r failed permanently for %s: %s", step, video_id, exc)
        fail_pipeline(video_id, step, str(exc))
        raise
    except TransientProviderError as exc:
        retries_so_far = self.request.retries
        max_retries = self.max_retries if self.max_retries is not None else 0
        if retries_so_far >= max_retries:
            logger.warning(
                "Pipeline step %r gave up after %d retries for %s: %s",
                step, retries_so_far, video_id, exc,
            )  # fmt: skip
            fail_pipeline(video_id, step, f"Gave up after {retries_so_far} retries: {exc}")
            raise
        delay = min(RETRY_BASE_DELAY_SECONDS * (2**retries_so_far), RETRY_MAX_DELAY_SECONDS)
        logger.info(
            "Pipeline step %r hit a transient error for %s (retry %d/%d in %ds): %s",
            step, video_id, retries_so_far + 1, max_retries, delay, exc,
        )  # fmt: skip
        raise self.retry(exc=exc, countdown=delay) from exc
    except Exception as exc:
        logger.exception("Unexpected error in pipeline step %r for video %s", step, video_id)
        fail_pipeline(video_id, step, f"Unexpected error: {exc}")
        raise
