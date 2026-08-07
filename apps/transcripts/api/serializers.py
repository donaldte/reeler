from rest_framework import serializers

from apps.transcripts.models import Transcript, TranscriptSegment


class TranscriptSegmentSerializer(serializers.ModelSerializer):
    class Meta:
        model = TranscriptSegment
        fields = ["index", "start_time", "end_time", "text", "confidence", "speaker_label"]


class TranscriptSerializer(serializers.ModelSerializer):
    segments = TranscriptSegmentSerializer(many=True, read_only=True)

    class Meta:
        model = Transcript
        fields = [
            "id",
            "video",
            "language",
            "language_confidence",
            "full_text",
            "provider",
            "model_name",
            "segments",
            "created_at",
        ]
        read_only_fields = fields
