from django.contrib import admin

from .models import AnalysisResult, BrollAsset, Highlight


class HighlightInline(admin.TabularInline):
    model = Highlight
    extra = 0
    readonly_fields = (
        "rank",
        "start_time",
        "end_time",
        "rationale",
        "score",
        "suggested_clip_title",
    )


class BrollAssetInline(admin.TabularInline):
    model = BrollAsset
    extra = 0
    readonly_fields = (
        "query",
        "start_time",
        "end_time",
        "image",
        "source_provider",
        "source_id",
    )


@admin.register(AnalysisResult)
class AnalysisResultAdmin(admin.ModelAdmin):
    list_display = ("video", "suggested_title", "llm_provider", "llm_model", "created_at")
    inlines = [HighlightInline, BrollAssetInline]
