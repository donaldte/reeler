from django.contrib import admin

from .models import ExportSettings


@admin.register(ExportSettings)
class ExportSettingsAdmin(admin.ModelAdmin):
    list_display = (
        "video",
        "num_highlights",
        "ai_creativity_level",
        "aspect_ratio",
        "video_quality",
        "created_at",
    )
    list_filter = ("ai_creativity_level", "aspect_ratio", "video_quality")
