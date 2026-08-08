from django.contrib import admin

from .models import RenderJob


@admin.register(RenderJob)
class RenderJobAdmin(admin.ModelAdmin):
    list_display = ("video", "status", "progress_percent", "stage", "created_at")
    list_filter = ("status",)
    readonly_fields = ("settings_snapshot", "progress_percent", "stage")
