from unittest.mock import patch

import pytest
from rest_framework import status
from rest_framework.test import APIClient

from apps.export_settings.models import ExportSettings
from apps.export_settings.tests.factories import ExportSettingsFactory
from apps.videos.models import UploadedVideo
from apps.videos.tests.factories import UploadedVideoFactory, UserFactory

pytestmark = pytest.mark.django_db


@pytest.fixture
def api_client():
    return APIClient()


def _url(video_id) -> str:
    return f"/api/v1/videos/{video_id}/settings/"


def test_retrieve_requires_auth(api_client):
    video = UploadedVideoFactory()
    response = api_client.get(_url(video.id))
    assert response.status_code == status.HTTP_403_FORBIDDEN


def test_retrieve_creates_default_settings_on_first_touch(api_client):
    owner = UserFactory()
    video = UploadedVideoFactory(project__owner=owner)
    api_client.force_authenticate(owner)

    response = api_client.get(_url(video.id))

    assert response.status_code == status.HTTP_200_OK
    assert response.data["num_highlights"] == 3
    assert ExportSettings.objects.filter(video=video).count() == 1


def test_retrieve_scoped_to_owner(api_client):
    owner = UserFactory()
    other = UserFactory()
    video = UploadedVideoFactory(project__owner=owner)
    api_client.force_authenticate(other)

    response = api_client.get(_url(video.id))

    assert response.status_code == status.HTTP_404_NOT_FOUND


def test_partial_update_saves_fields(api_client):
    owner = UserFactory()
    video = UploadedVideoFactory(project__owner=owner)
    ExportSettingsFactory(video=video, num_highlights=3)
    api_client.force_authenticate(owner)

    response = api_client.patch(_url(video.id), {"num_highlights": 7}, format="json")

    assert response.status_code == status.HTTP_200_OK
    assert response.data["num_highlights"] == 7
    assert ExportSettings.objects.filter(video=video).latest("created_at").num_highlights == 7


def test_partial_update_triggers_rerun_on_live_field_change_when_completed(api_client):
    owner = UserFactory()
    video = UploadedVideoFactory(project__owner=owner, status=UploadedVideo.Status.COMPLETED)
    ExportSettingsFactory(video=video, num_highlights=3)
    api_client.force_authenticate(owner)

    with patch("apps.videos.tasks.rerun_analysis_only") as mock_rerun:
        response = api_client.patch(_url(video.id), {"num_highlights": 9}, format="json")

    assert response.data["rerun_triggered"] is True
    mock_rerun.assert_called_once_with(str(video.id))


def test_partial_update_does_not_trigger_rerun_for_inert_field(api_client):
    owner = UserFactory()
    video = UploadedVideoFactory(project__owner=owner, status=UploadedVideo.Status.COMPLETED)
    ExportSettingsFactory(video=video)
    api_client.force_authenticate(owner)

    with patch("apps.videos.tasks.rerun_analysis_only") as mock_rerun:
        response = api_client.patch(
            _url(video.id), {"music_style": ExportSettings.MusicStyle.CINEMATIC}, format="json"
        )

    assert response.data["rerun_triggered"] is False
    mock_rerun.assert_not_called()
