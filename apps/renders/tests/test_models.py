import pytest

from apps.renders.models import RenderJob
from apps.renders.tests.factories import RenderJobFactory

pytestmark = pytest.mark.django_db


def test_defaults():
    render_job = RenderJobFactory()
    assert render_job.status == RenderJob.Status.PENDING
    assert render_job.progress_percent == 0
    assert render_job.stage == ""
    assert render_job.error_message == ""
    assert not render_job.output_file


def test_is_terminal_false_for_pending_and_rendering():
    assert RenderJobFactory(status=RenderJob.Status.PENDING).is_terminal is False
    assert RenderJobFactory(status=RenderJob.Status.RENDERING).is_terminal is False


@pytest.mark.parametrize("status", [RenderJob.Status.COMPLETED, RenderJob.Status.FAILED])
def test_is_terminal_true_for_completed_and_failed(status):
    assert RenderJobFactory(status=status).is_terminal is True


def test_str():
    render_job = RenderJobFactory()
    assert str(render_job.video_id) in str(render_job)
    assert render_job.status in str(render_job)


def test_multiple_render_jobs_allowed_per_video():
    video = RenderJobFactory().video
    RenderJobFactory(video=video)
    RenderJobFactory(video=video)
    assert video.render_jobs.count() == 3
