from rest_framework import serializers

from apps.renders.models import RenderJob


class RenderJobSerializer(serializers.ModelSerializer):
    class Meta:
        model = RenderJob
        fields = [
            "id",
            "video",
            "status",
            "progress_percent",
            "stage",
            "output_file",
            "error_message",
            "settings_snapshot",
            "created_at",
            "updated_at",
        ]
        read_only_fields = fields
