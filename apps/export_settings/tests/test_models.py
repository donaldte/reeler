import pytest

from apps.export_settings.models import ExportSettings
from apps.export_settings.tests.factories import ExportSettingsFactory

pytestmark = pytest.mark.django_db


def test_defaults():
    settings_obj = ExportSettingsFactory()
    assert settings_obj.num_highlights == 3
    assert settings_obj.ai_creativity_level == ExportSettings.AiCreativityLevel.BALANCED
    assert settings_obj.aspect_ratio == ExportSettings.AspectRatio.VERTICAL
    assert settings_obj.output_duration_seconds == 60
    assert settings_obj.export_mode == ExportSettings.ExportMode.HIGHLIGHT_REEL
    assert not settings_obj.logo_image
    assert settings_obj.image_generation_enabled is False
    assert settings_obj.internet_media_search_enabled is False


def test_num_highlights_and_duration_accept_generous_values():
    """Regression test: these were capped at 10/240 respectively, which
    made a longer highlight reel or export_mode=full_video's 'catch as
    many highlights as possible' use case unreachable.
    """
    settings_obj = ExportSettingsFactory(num_highlights=30, output_duration_seconds=3600)
    settings_obj.full_clean()
    assert settings_obj.num_highlights == 30
    assert settings_obj.output_duration_seconds == 3600


@pytest.mark.parametrize(
    ("level", "expected_temperature"),
    [
        (ExportSettings.AiCreativityLevel.CONSERVATIVE, 0.2),
        (ExportSettings.AiCreativityLevel.BALANCED, 0.5),
        (ExportSettings.AiCreativityLevel.CREATIVE, 0.9),
    ],
)
def test_temperature_property_maps_creativity_level(level, expected_temperature):
    settings_obj = ExportSettingsFactory(ai_creativity_level=level)
    assert settings_obj.temperature == expected_temperature


def test_str():
    settings_obj = ExportSettingsFactory()
    assert str(settings_obj.video_id) in str(settings_obj)


def test_multiple_settings_allowed_per_video():
    """FK, not O2O -- phase 3 will support multiple render variants."""
    video = ExportSettingsFactory().video
    ExportSettingsFactory(video=video)
    ExportSettingsFactory(video=video)
    assert video.export_settings_list.count() == 3
