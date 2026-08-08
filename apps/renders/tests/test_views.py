from unittest.mock import patch

import pytest
from django.urls import reverse

from apps.highlights.models import AnalysisResult
from apps.renders.models import RenderJob
from apps.renders.tests.factories import RenderJobFactory
from apps.videos.models import UploadedVideo
from apps.videos.tests.factories import UploadedVideoFactory, UserFactory

pytestmark = pytest.mark.django_db


def _start_url(video_id) -> str:
    return reverse("renders:start", args=[video_id])


def _completed_video_with_highlights(owner):
    video = UploadedVideoFactory(project__owner=owner, status=UploadedVideo.Status.COMPLETED)
    result = AnalysisResult.objects.create(
        video=video, summary="s", suggested_title="t", suggested_description="d",
        suggested_hashtags=[], llm_provider="ollama", llm_model="qwen2.5:3b", raw_response={},
    )  # fmt: skip
    result.highlights.create(rank=1, start_time=0.0, end_time=2.0, rationale="r")
    return video


def test_start_requires_login(client):
    video = UploadedVideoFactory()
    response = client.post(_start_url(video.id))
    assert response.status_code == 302
    assert "/accounts/login" in response.url


def test_start_requires_post(client):
    owner = UserFactory()
    video = UploadedVideoFactory(project__owner=owner)
    client.force_login(owner)
    response = client.get(_start_url(video.id))
    assert response.status_code == 405


def test_start_returns_404_for_another_users_video(client):
    owner = UserFactory()
    other = UserFactory()
    video = UploadedVideoFactory(project__owner=owner)
    client.force_login(other)
    response = client.post(_start_url(video.id))
    assert response.status_code == 404


def test_start_launches_render_job_and_redirects(client):
    owner = UserFactory()
    video = _completed_video_with_highlights(owner)
    client.force_login(owner)

    with patch("apps.renders.tasks.render_video_task.delay") as mock_delay:
        response = client.post(_start_url(video.id))

    assert response.status_code == 302
    assert response.url == reverse("videos:detail", args=[video.id])
    assert RenderJob.objects.filter(video=video).count() == 1
    mock_delay.assert_called_once()


def test_start_on_unready_video_flashes_error_and_does_not_create_job(client):
    owner = UserFactory()
    video = UploadedVideoFactory(project__owner=owner, status=UploadedVideo.Status.ANALYZING)
    client.force_login(owner)

    response = client.post(_start_url(video.id), follow=True)

    assert RenderJob.objects.filter(video=video).count() == 0
    messages = [str(m) for m in response.context["messages"]]
    assert any("must complete" in m for m in messages)


def test_status_fragment_requires_login(client):
    render_job = RenderJobFactory()
    url = reverse("renders:status_fragment", args=[render_job.id])
    response = client.get(url)
    assert response.status_code == 302


def test_status_fragment_scoped_to_owner(client):
    owner = UserFactory()
    other = UserFactory()
    video = UploadedVideoFactory(project__owner=owner)
    render_job = RenderJobFactory(video=video)
    client.force_login(other)

    url = reverse("renders:status_fragment", args=[render_job.id])
    response = client.get(url)

    assert response.status_code == 404


def test_status_fragment_renders_for_owner(client):
    owner = UserFactory()
    video = UploadedVideoFactory(project__owner=owner)
    render_job = RenderJobFactory(
        video=video, status=RenderJob.Status.RENDERING, progress_percent=42
    )
    client.force_login(owner)

    url = reverse("renders:status_fragment", args=[render_job.id])
    response = client.get(url)

    assert response.status_code == 200
    assert b"42%" in response.content


def test_completed_render_shows_download_link(client):
    from django.core.files.base import ContentFile

    owner = UserFactory()
    video = UploadedVideoFactory(project__owner=owner)
    render_job = RenderJobFactory(
        video=video, status=RenderJob.Status.COMPLETED, progress_percent=100
    )
    render_job.output_file.save("out.mp4", ContentFile(b"fake"), save=True)
    client.force_login(owner)

    url = reverse("renders:status_fragment", args=[render_job.id])
    response = client.get(url)

    assert response.status_code == 200
    assert b"Download" in response.content


def test_video_detail_page_shows_render_section(client):
    owner = UserFactory()
    video = _completed_video_with_highlights(owner)
    client.force_login(owner)

    response = client.get(reverse("videos:detail", args=[video.id]))

    assert response.status_code == 200
    assert b"Render short video" in response.content
