from rest_framework import serializers

from apps.export_settings.models import ExportSettings


class ExportSettingsSerializer(serializers.ModelSerializer):
    class Meta:
        model = ExportSettings
        exclude = ["video"]
        read_only_fields = ["id", "created_at", "updated_at"]
