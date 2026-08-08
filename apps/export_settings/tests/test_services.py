from unittest.mock import patch

import pytest

from apps.export_settings.models import ExportSettings
from apps.export_settings.services import get_or_create_export_settings, maybe_rerun_analysis
from apps.export_settings.tests.factories import ExportSettingsFactory
from apps.videos.models import UploadedVideo
from apps.videos.tests.factories import UploadedVideoFactory

pytestmark = pytest.mark.django_db


def test_get_or_create_export_settings_creates_default_when_none_exist():
    video = UploadedVideoFactory()
    assert ExportSettings.objects.filter(video=video).count() == 0

    settings_obj = get_or_create_export_settings(video)

    assert settings_obj.video_id == video.id
    assert ExportSettings.objects.filter(video=video).count() == 1


def test_get_or_create_export_settings_reuses_latest_existing_row():
    video = UploadedVideoFactory()
    older = ExportSettingsFactory(video=video, num_highlights=5)
    newer = ExportSettingsFactory(video=video, num_highlights=7)

    settings_obj = get_or_create_export_settings(video)

    assert settings_obj.id == newer.id
    assert settings_obj.id != older.id
    assert ExportSettings.objects.filter(video=video).count() == 2  # no new row created


def test_maybe_rerun_analysis_triggers_on_live_field_change_when_completed():
    video = UploadedVideoFactory(status=UploadedVideo.Status.COMPLETED)

    with patch("apps.videos.tasks.rerun_analysis_only") as mock_rerun:
        did_rerun = maybe_rerun_analysis(video, {"num_highlights"})

    assert did_rerun is True
    mock_rerun.assert_called_once_with(str(video.id))


def test_maybe_rerun_analysis_skips_when_video_not_completed():
    video = UploadedVideoFactory(status=UploadedVideo.Status.ANALYZING)

    with patch("apps.videos.tasks.rerun_analysis_only") as mock_rerun:
        did_rerun = maybe_rerun_analysis(video, {"ai_creativity_level"})

    assert did_rerun is False
    mock_rerun.assert_not_called()


def test_maybe_rerun_analysis_skips_when_only_inert_fields_changed():
    video = UploadedVideoFactory(status=UploadedVideo.Status.COMPLETED)

    with patch("apps.videos.tasks.rerun_analysis_only") as mock_rerun:
        did_rerun = maybe_rerun_analysis(video, {"aspect_ratio", "music_style"})

    assert did_rerun is False
    mock_rerun.assert_not_called()


def test_maybe_rerun_analysis_skips_when_nothing_changed():
    video = UploadedVideoFactory(status=UploadedVideo.Status.COMPLETED)

    with patch("apps.videos.tasks.rerun_analysis_only") as mock_rerun:
        did_rerun = maybe_rerun_analysis(video, set())

    assert did_rerun is False
    mock_rerun.assert_not_called()
