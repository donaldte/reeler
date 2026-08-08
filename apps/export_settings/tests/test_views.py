from unittest.mock import patch

import pytest
from django.urls import reverse

from apps.export_settings.models import ExportSettings
from apps.videos.models import UploadedVideo
from apps.videos.tests.factories import UploadedVideoFactory, UserFactory

pytestmark = pytest.mark.django_db


def _save_url(video_id) -> str:
    return reverse("export_settings:save", args=[video_id])


def test_save_requires_login(client):
    video = UploadedVideoFactory()
    response = client.post(_save_url(video.id), {"num_highlights": 5})
    assert response.status_code == 302
    assert "/accounts/login" in response.url


def test_save_requires_post(client):
    owner = UserFactory()
    video = UploadedVideoFactory(project__owner=owner)
    client.force_login(owner)

    response = client.get(_save_url(video.id))

    assert response.status_code == 405


def test_save_returns_404_for_another_users_video(client):
    owner = UserFactory()
    other = UserFactory()
    video = UploadedVideoFactory(project__owner=owner)
    client.force_login(other)

    response = client.post(_save_url(video.id), {"num_highlights": 5})

    assert response.status_code == 404


def test_valid_post_saves_settings_and_redirects(client):
    owner = UserFactory()
    video = UploadedVideoFactory(project__owner=owner, status=UploadedVideo.Status.PENDING)
    client.force_login(owner)

    form_data = {
        "num_highlights": 6,
        "ai_creativity_level": ExportSettings.AiCreativityLevel.CREATIVE,
        "output_duration_seconds": 90,
        "aspect_ratio": ExportSettings.AspectRatio.SQUARE,
        "caption_style": ExportSettings.CaptionStyle.MINIMAL,
        "font": ExportSettings.FontChoice.ROBOTO,
        "color_theme": ExportSettings.ColorTheme.VIBRANT,
        "transition_style": ExportSettings.TransitionStyle.ZOOM,
        "music_style": ExportSettings.MusicStyle.UPBEAT,
        "subtitle_language": "auto",
        "voice_over_style": ExportSettings.VoiceOverStyle.NONE,
        "broll_type": ExportSettings.BrollType.NONE,
        "video_quality": ExportSettings.VideoQuality.Q_1080P,
        "export_format": ExportSettings.ExportFormat.MP4,
    }

    response = client.post(_save_url(video.id), form_data)

    assert response.status_code == 302
    assert response.url == reverse("videos:detail", args=[video.id])
    settings_obj = ExportSettings.objects.get(video=video)
    assert settings_obj.num_highlights == 6
    assert settings_obj.ai_creativity_level == ExportSettings.AiCreativityLevel.CREATIVE
    assert settings_obj.aspect_ratio == ExportSettings.AspectRatio.SQUARE


def test_valid_post_triggers_rerun_when_completed_and_live_field_changed(client):
    owner = UserFactory()
    video = UploadedVideoFactory(project__owner=owner, status=UploadedVideo.Status.COMPLETED)
    client.force_login(owner)

    form_data = {
        "num_highlights": 8,
        "ai_creativity_level": ExportSettings.AiCreativityLevel.BALANCED,
        "output_duration_seconds": 60,
        "aspect_ratio": ExportSettings.AspectRatio.VERTICAL,
        "caption_style": ExportSettings.CaptionStyle.BOLD,
        "font": ExportSettings.FontChoice.INTER,
        "color_theme": ExportSettings.ColorTheme.DEFAULT,
        "transition_style": ExportSettings.TransitionStyle.FADE,
        "music_style": ExportSettings.MusicStyle.NONE,
        "subtitle_language": "auto",
        "voice_over_style": ExportSettings.VoiceOverStyle.NONE,
        "broll_type": ExportSettings.BrollType.NONE,
        "video_quality": ExportSettings.VideoQuality.Q_1080P,
        "export_format": ExportSettings.ExportFormat.MP4,
    }

    with patch("apps.videos.tasks.rerun_analysis_only") as mock_rerun:
        response = client.post(_save_url(video.id), form_data, follow=True)

    mock_rerun.assert_called_once_with(str(video.id))
    messages = [str(m) for m in response.context["messages"]]
    assert any("re-running analysis" in m for m in messages)


def test_invalid_post_flashes_error_and_redirects(client):
    owner = UserFactory()
    video = UploadedVideoFactory(project__owner=owner)
    client.force_login(owner)

    response = client.post(_save_url(video.id), {"num_highlights": 999}, follow=True)

    assert response.status_code == 200
    messages = [str(m) for m in response.context["messages"]]
    assert any("Couldn't save settings" in m for m in messages)


def test_detail_page_renders_embedded_settings_form(client):
    owner = UserFactory()
    video = UploadedVideoFactory(project__owner=owner, status=UploadedVideo.Status.COMPLETED)
    client.force_login(owner)

    response = client.get(reverse("videos:detail", args=[video.id]))

    assert response.status_code == 200
    assert b"Customize" in response.content
    assert _save_url(video.id).encode() in response.content
