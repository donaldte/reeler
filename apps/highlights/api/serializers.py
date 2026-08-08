from rest_framework import serializers

from apps.highlights.models import AnalysisResult, BrollAsset, Highlight


class HighlightSerializer(serializers.ModelSerializer):
    class Meta:
        model = Highlight
        fields = [
            "rank",
            "start_time",
            "end_time",
            "rationale",
            "score",
            "suggested_clip_title",
            "emoji",
            "transition",
        ]


class BrollAssetSerializer(serializers.ModelSerializer):
    class Meta:
        model = BrollAsset
        fields = ["query", "start_time", "end_time", "image", "source_provider"]


class AnalysisResultSerializer(serializers.ModelSerializer):
    highlights = HighlightSerializer(many=True, read_only=True)
    broll_assets = BrollAssetSerializer(many=True, read_only=True)

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
            "broll_assets",
            "created_at",
        ]
        read_only_fields = fields
