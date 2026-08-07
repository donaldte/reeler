from django.contrib import admin

from .models import Transcript, TranscriptSegment


class TranscriptSegmentInline(admin.TabularInline):
    model = TranscriptSegment
    extra = 0
    readonly_fields = ("index", "start_time", "end_time", "text", "confidence", "speaker_label")


@admin.register(Transcript)
class TranscriptAdmin(admin.ModelAdmin):
    list_display = ("video", "language", "provider", "model_name", "created_at")
    inlines = [TranscriptSegmentInline]
