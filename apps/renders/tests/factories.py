import factory

from apps.renders.models import RenderJob
from apps.videos.tests.factories import UploadedVideoFactory

DEFAULT_SNAPSHOT = {
    "output_duration_seconds": 60,
    "aspect_ratio": "9:16",
    "caption_style": "bold",
    "font": "inter",
    "color_theme": "default",
    "transition_style": "fade",
    "subtitle_language": "auto",
    "video_quality": "1080p",
    "export_format": "mp4",
}


class RenderJobFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = RenderJob

    video = factory.SubFactory(UploadedVideoFactory)
    settings_snapshot = factory.LazyFunction(lambda: dict(DEFAULT_SNAPSHOT))
