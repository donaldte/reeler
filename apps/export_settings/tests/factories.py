import factory

from apps.export_settings.models import ExportSettings
from apps.videos.tests.factories import UploadedVideoFactory


class ExportSettingsFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = ExportSettings

    video = factory.SubFactory(UploadedVideoFactory)
