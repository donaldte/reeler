from rest_framework import serializers

from apps.highlights.models import AnalysisResult, Highlight


class HighlightSerializer(serializers.ModelSerializer):
    class Meta:
        model = Highlight
        fields = ["rank", "start_time", "end_time", "rationale", "score", "suggested_clip_title"]


class AnalysisResultSerializer(serializers.ModelSerializer):
    highlights = HighlightSerializer(many=True, read_only=True)

    class Meta:
        model = AnalysisResult
        fields = [
            "id",
            "video",
            "summary",
            "suggested_title",
            "suggested_description",
            "suggested_hashtags",
            "llm_provider",
            "llm_model",
            "highlights",
            "created_at",
        ]
        read_only_fields = fields
