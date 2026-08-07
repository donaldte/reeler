from unittest.mock import patch

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from rest_framework import status
from rest_framework.test import APIClient

from apps.videos.tests.factories import UploadedVideoFactory, UserFactory

pytestmark = pytest.mark.django_db


@pytest.fixture
def api_client():
    return APIClient()


def test_create_video_requires_auth(api_client):
    upload = SimpleUploadedFile("clip.mp4", b"fake", content_type="video/mp4")
    response = api_client.post("/api/v1/videos/", {"file": upload}, format="multipart")
    assert response.status_code == status.HTTP_403_FORBIDDEN


def test_create_video_launches_pipeline(api_client):
    user = UserFactory()
    api_client.force_authenticate(user)
    upload = SimpleUploadedFile("clip.mp4", b"fake", content_type="video/mp4")

    with patch("apps.videos.tasks.run_analysis_pipeline") as mock_pipeline:
        response = api_client.post("/api/v1/videos/", {"file": upload}, format="multipart")

    assert response.status_code == status.HTTP_201_CREATED
    assert response.data["status"] == "pending"
    mock_pipeline.assert_called_once()


def test_list_videos_scoped_to_owner(api_client):
    owner = UserFactory()
    other = UserFactory()
    UploadedVideoFactory(project__owner=owner)
    UploadedVideoFactory(project__owner=other)

    api_client.force_authenticate(owner)
    response = api_client.get("/api/v1/videos/")

    assert response.status_code == status.HTTP_200_OK
    assert response.data["count"] == 1


def test_status_action_returns_pipeline_state(api_client):
    owner = UserFactory()
    video = UploadedVideoFactory(project__owner=owner, status="completed", progress_percent=100)

    api_client.force_authenticate(owner)
    response = api_client.get(f"/api/v1/videos/{video.id}/status/")

    assert response.status_code == status.HTTP_200_OK
    assert response.data["status"] == "completed"
    assert response.data["progress_percent"] == 100
