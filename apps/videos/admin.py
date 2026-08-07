from django.contrib import admin

from .models import Project, UploadedVideo


@admin.register(Project)
class ProjectAdmin(admin.ModelAdmin):
    list_display = ("title", "owner", "created_at")
    search_fields = ("title", "owner__username")


@admin.register(UploadedVideo)
class UploadedVideoAdmin(admin.ModelAdmin):
    list_display = ("original_filename", "project", "status", "progress_percent", "created_at")
    list_filter = ("status",)
    readonly_fields = (
        "duration_seconds",
        "width",
        "height",
        "fps",
        "has_audio",
        "video_codec",
        "audio_codec",
        "pipeline_steps",
    )
    search_fields = ("original_filename",)
