from unittest.mock import patch

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse

from apps.highlights.models import AnalysisResult
from apps.videos.models import UploadedVideo
from apps.videos.tests.factories import UploadedVideoFactory, UserFactory

pytestmark = pytest.mark.django_db


def test_upload_requires_login(client):
    response = client.get(reverse("videos:upload"))
    assert response.status_code == 302


def test_upload_get_renders_form(client):
    client.force_login(UserFactory())
    response = client.get(reverse("videos:upload"))
    assert response.status_code == 200
    assert b"Upload" in response.content


def test_upload_post_creates_video_and_redirects(client):
    client.force_login(UserFactory())
    upload = SimpleUploadedFile("clip.mp4", b"fake", content_type="video/mp4")

    with patch("apps.videos.tasks.run_analysis_pipeline") as mock_pipeline:
        response = client.post(reverse("videos:upload"), {"file": upload})

    assert response.status_code == 302
    mock_pipeline.assert_called_once()


def test_upload_post_rejects_unsupported_extension(client):
    client.force_login(UserFactory())
    upload = SimpleUploadedFile("notes.txt", b"fake", content_type="text/plain")

    response = client.post(reverse("videos:upload"), {"file": upload})

    assert response.status_code == 200
    assert b"Unsupported file type" in response.content


def test_detail_requires_ownership(client):
    owner = UserFactory()
    other = UserFactory()
    video = UploadedVideoFactory(project__owner=owner)
    client.force_login(other)

    response = client.get(reverse("videos:detail", args=[video.id]))

    assert response.status_code == 404


def test_detail_renders_for_owner(client):
    owner = UserFactory()
    video = UploadedVideoFactory(project__owner=owner)
    client.force_login(owner)

    response = client.get(reverse("videos:detail", args=[video.id]))

    assert response.status_code == 200


def test_detail_page_shows_broll_assets_with_query_and_timestamps(client):
    owner = UserFactory()
    video = UploadedVideoFactory(project__owner=owner, status=UploadedVideo.Status.COMPLETED)
    result = AnalysisResult.objects.create(
        video=video, summary="s", suggested_title="t", suggested_description="d",
        suggested_hashtags=[], llm_provider="ollama", llm_model="qwen2.5:3b", raw_response={},
    )  # fmt: skip
    result.highlights.create(rank=1, start_time=0.0, end_time=10.0, rationale="r")
    result.broll_assets.create(query="laptop coding closeup", start_time=2.0, end_time=5.0)
    client.force_login(owner)

    response = client.get(reverse("videos:detail", args=[video.id]))

    assert response.status_code == 200
    assert b"laptop coding closeup" in response.content
    assert b"no image found" in response.content  # no image downloaded in this test


def test_status_fragment_renders(client):
    owner = UserFactory()
    video = UploadedVideoFactory(project__owner=owner)
    client.force_login(owner)

    response = client.get(reverse("videos:status_fragment", args=[video.id]))

    assert response.status_code == 200
    assert b"video-status" in response.content
