from rest_framework import serializers

from apps.videos.models import UploadedVideo


class UploadedVideoSerializer(serializers.ModelSerializer):
    class Meta:
        model = UploadedVideo
        fields = [
            "id",
            "project",
            "original_filename",
            "file_size_bytes",
            "duration_seconds",
            "width",
            "height",
            "fps",
            "has_audio",
            "video_codec",
            "audio_codec",
            "status",
            "progress_percent",
            "pipeline_steps",
            "error_message",
            "created_at",
            "updated_at",
        ]
        read_only_fields = fields


class VideoUploadSerializer(serializers.Serializer):
    file = serializers.FileField()
