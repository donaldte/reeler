from unittest.mock import patch

import pytest
from rest_framework import status
from rest_framework.test import APIClient

from apps.highlights.models import AnalysisResult
from apps.renders.models import RenderJob
from apps.renders.tests.factories import RenderJobFactory
from apps.videos.models import UploadedVideo
from apps.videos.tests.factories import UploadedVideoFactory, UserFactory

pytestmark = pytest.mark.django_db


@pytest.fixture
def api_client():
    return APIClient()


def _completed_video_with_highlights(owner):
    video = UploadedVideoFactory(project__owner=owner, status=UploadedVideo.Status.COMPLETED)
    result = AnalysisResult.objects.create(
        video=video, summary="s", suggested_title="t", suggested_description="d",
        suggested_hashtags=[], llm_provider="ollama", llm_model="qwen2.5:3b", raw_response={},
    )  # fmt: skip
    result.highlights.create(rank=1, start_time=0.0, end_time=2.0, rationale="r")
    return video


def test_create_render_requires_auth(api_client):
    video = UploadedVideoFactory()
    response = api_client.post(f"/api/v1/videos/{video.id}/renders/")
    assert response.status_code == status.HTTP_403_FORBIDDEN


def test_create_render_success(api_client):
    owner = UserFactory()
    video = _completed_video_with_highlights(owner)
    api_client.force_authenticate(owner)

    with patch("apps.renders.tasks.render_video_task.delay") as mock_delay:
        response = api_client.post(f"/api/v1/videos/{video.id}/renders/")

    assert response.status_code == status.HTTP_201_CREATED
    assert response.data["status"] == "pending"
    mock_delay.assert_called_once()


def test_create_render_on_unready_video_returns_400(api_client):
    owner = UserFactory()
    video = UploadedVideoFactory(project__owner=owner, status=UploadedVideo.Status.ANALYZING)
    api_client.force_authenticate(owner)

    response = api_client.post(f"/api/v1/videos/{video.id}/renders/")

    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert response.data["error"]["code"] == "not_ready"


def test_create_render_scoped_to_owner(api_client):
    owner = UserFactory()
    other = UserFactory()
    video = _completed_video_with_highlights(owner)
    api_client.force_authenticate(other)

    response = api_client.post(f"/api/v1/videos/{video.id}/renders/")

    assert response.status_code == status.HTTP_404_NOT_FOUND


def test_list_renders_scoped_to_owner(api_client):
    owner = UserFactory()
    other = UserFactory()
    video_a = UploadedVideoFactory(project__owner=owner)
    video_b = UploadedVideoFactory(project__owner=other)
    RenderJobFactory(video=video_a)
    RenderJobFactory(video=video_b)
    api_client.force_authenticate(owner)

    response = api_client.get(f"/api/v1/videos/{video_a.id}/renders/")

    assert response.status_code == status.HTTP_200_OK
    assert response.data["count"] == 1


def test_render_job_detail_returns_status(api_client):
    owner = UserFactory()
    video = UploadedVideoFactory(project__owner=owner)
    render_job = RenderJobFactory(
        video=video, status=RenderJob.Status.RENDERING, progress_percent=30
    )
    api_client.force_authenticate(owner)

    response = api_client.get(f"/api/v1/render-jobs/{render_job.id}/")

    assert response.status_code == status.HTTP_200_OK
    assert response.data["status"] == "rendering"
    assert response.data["progress_percent"] == 30


def test_render_job_detail_scoped_to_owner(api_client):
    owner = UserFactory()
    other = UserFactory()
    video = UploadedVideoFactory(project__owner=owner)
    render_job = RenderJobFactory(video=video)
    api_client.force_authenticate(other)

    response = api_client.get(f"/api/v1/render-jobs/{render_job.id}/")

    assert response.status_code == status.HTTP_404_NOT_FOUND
