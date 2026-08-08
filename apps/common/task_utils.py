"""Shared Celery failure-handling, used by every pipeline task across apps.

`@shared_task(..., autoretry_for=(TransientProviderError,))` looks
appealing but has a sharp edge: Celery implements it by wrapping the whole
task call *outside* the function body, so when retries are finally
exhausted, the re-raised exception happens in code the task function has
already exited — nothing inside the function (however broad the
try/except) ever sees it. The practical symptom: a task's owning record
gets stuck showing an in-progress status forever, no error, no way to know
it failed.

`task_failure_guard` fixes this by doing retries manually (`self.retry()`
called from *inside* the guarded block, so we control exactly what happens
when retries run out) and by adding a last-resort `except Exception` so
literally any failure — a permanent error, a transient one that ran out of
retries, a Celery soft-time-limit, a bug — always calls `on_failure` with
a clear message, never silently stuck. See docs/ai_pipeline.md.

Originally lived in `apps/videos/task_utils.py` as `pipeline_task_guard`
(hardcoded to `UploadedVideo`'s status fields); extracted here once
`apps/renders` needed the identical mechanism for `RenderJob`.
`pipeline_task_guard` is now a thin wrapper around this — see that module.
"""

import logging
from collections.abc import Callable, Generator
from contextlib import contextmanager

from celery import Task

from domain.exceptions import PermanentPipelineError, TransientProviderError

logger = logging.getLogger("reeler")

RETRY_BASE_DELAY_SECONDS = 60
RETRY_MAX_DELAY_SECONDS = 900


@contextmanager
def task_failure_guard(
    self: Task, *, label: str, on_failure: Callable[[str], None]
) -> Generator[None]:
    """Wrap a Celery task's body in this. On any failure it calls
    `on_failure(message)` before re-raising, except for a
    `TransientProviderError` that still has retries left — that one
    triggers `self.retry()` instead.

    Usage:
        @shared_task(bind=True, acks_late=True, max_retries=3)
        def some_task(self: Task, job_id: str) -> str:
            with task_failure_guard(self, label=f"... {job_id}", on_failure=lambda msg: ...):
                ...  # do the work; raise PermanentPipelineError /
                     # TransientProviderError as appropriate
            return job_id
    """
    try:
        yield
    except PermanentPipelineError as exc:
        logger.warning("%s failed permanently: %s", label, exc)
        on_failure(str(exc))
        raise
    except TransientProviderError as exc:
        retries_so_far = self.request.retries
        max_retries = self.max_retries if self.max_retries is not None else 0
        if retries_so_far >= max_retries:
            logger.warning("%s gave up after %d retries: %s", label, retries_so_far, exc)
            on_failure(f"Gave up after {retries_so_far} retries: {exc}")
            raise
        delay = min(RETRY_BASE_DELAY_SECONDS * (2**retries_so_far), RETRY_MAX_DELAY_SECONDS)
        logger.info(
            "%s hit a transient error (retry %d/%d in %ds): %s",
            label, retries_so_far + 1, max_retries, delay, exc,
        )  # fmt: skip
        raise self.retry(exc=exc, countdown=delay) from exc
    except Exception as exc:
        logger.exception("Unexpected error in %s", label)
        on_failure(f"Unexpected error: {exc}")
        raise
