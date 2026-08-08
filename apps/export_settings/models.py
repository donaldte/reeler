from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models

from apps.common.models import TimeStampedModel
from apps.videos.models import UploadedVideo


def upload_logo_path(instance: "ExportSettings", filename: str) -> str:
    return f"export_settings/{instance.video_id}/{instance.id}/{filename}"


class ExportSettings(TimeStampedModel):
    """User-configurable preferences for a video's analysis and (future)
    render. FK rather than O2O to `UploadedVideo` on purpose — the roadmap
    calls for supporting multiple render variants from one analysis later
    (phase 3). Phase 2 only ever works with the latest row per video, via
    `apps.export_settings.services.get_or_create_export_settings`.

    Two fields are "live" today (they actually change LLM behavior — see
    `apps/highlights/tasks.py::generate_analysis_task`):
    `num_highlights` and `ai_creativity_level`. Every other field is
    schema-complete but inert until the phase 3 renderer exists to read it
    — see docs/roadmap.md. The UI labels this distinction explicitly so
    saving them isn't misleading.
    """

    class AspectRatio(models.TextChoices):
        WIDESCREEN = "16:9", "16:9 (Widescreen)"
        VERTICAL = "9:16", "9:16 (Vertical / Shorts)"
        SQUARE = "1:1", "1:1 (Square)"

    class CaptionStyle(models.TextChoices):
        NONE = "none", "None"
        MINIMAL = "minimal", "Minimal"
        BOLD = "bold", "Bold"
        KARAOKE = "karaoke", "Karaoke (word-by-word)"

    class FontChoice(models.TextChoices):
        INTER = "inter", "Inter"
        MONTSERRAT = "montserrat", "Montserrat"
        ANTON = "anton", "Anton"
        ROBOTO = "roboto", "Roboto"

    class ColorTheme(models.TextChoices):
        DEFAULT = "default", "Default"
        VIBRANT = "vibrant", "Vibrant"
        DARK = "dark", "Dark"
        PASTEL = "pastel", "Pastel"
        MONOCHROME = "monochrome", "Monochrome"

    class TransitionStyle(models.TextChoices):
        NONE = "none", "None (hard cuts)"
        FADE = "fade", "Fade"
        SLIDE = "slide", "Slide"
        ZOOM = "zoom", "Zoom"

    class ExportMode(models.TextChoices):
        HIGHLIGHT_REEL = "highlight_reel", "Highlight reel"
        FULL_VIDEO = "full_video", "Full video (entire source, polished)"

    class MusicStyle(models.TextChoices):
        NONE = "none", "None"
        UPBEAT = "upbeat", "Upbeat"
        CHILL = "chill", "Chill"
        DRAMATIC = "dramatic", "Dramatic"
        CORPORATE = "corporate", "Corporate"
        CINEMATIC = "cinematic", "Cinematic"

    class VoiceOverStyle(models.TextChoices):
        NONE = "none", "None"
        MALE = "male", "Male"
        FEMALE = "female", "Female"
        NEUTRAL = "neutral", "Neutral"

    class AiCreativityLevel(models.TextChoices):
        CONSERVATIVE = "conservative", "Conservative"
        BALANCED = "balanced", "Balanced"
        CREATIVE = "creative", "Creative"

    class BrollType(models.TextChoices):
        NONE = "none", "None"
        STOCK_FOOTAGE = "stock_footage", "Stock footage"
        AI_GENERATED = "ai_generated", "AI-generated"
        MIXED = "mixed", "Mixed"

    class VideoQuality(models.TextChoices):
        Q_720P = "720p", "720p"
        Q_1080P = "1080p", "1080p"
        Q_4K = "4k", "4K"

    class ExportFormat(models.TextChoices):
        MP4 = "mp4", "MP4"
        MOV = "mov", "MOV"
        WEBM = "webm", "WebM"

    class LogoPosition(models.TextChoices):
        # Values must match domain.rendering.ffmpeg_commands.
        # WATERMARK_POSITION_EXPRESSIONS' keys exactly.
        TOP_LEFT = "top_left", "Top left"
        TOP_RIGHT = "top_right", "Top right"
        BOTTOM_LEFT = "bottom_left", "Bottom left"
        BOTTOM_RIGHT = "bottom_right", "Bottom right"

    # Maps AiCreativityLevel -> LLM sampling temperature. Not user-facing
    # directly — "creative" is a friendlier concept than a raw float.
    CREATIVITY_TEMPERATURE_MAP: dict[str, float] = {
        AiCreativityLevel.CONSERVATIVE: 0.2,
        AiCreativityLevel.BALANCED: 0.5,
        AiCreativityLevel.CREATIVE: 0.9,
    }

    video = models.ForeignKey(
        UploadedVideo, on_delete=models.CASCADE, related_name="export_settings_list"
    )

    # --- Live: actually affect analysis today ---
    num_highlights = models.PositiveSmallIntegerField(
        default=3,
        # 30, not some smaller "reasonable" number: a longer highlight
        # reel needs more highlights to fill it (see export_mode/
        # output_duration_seconds below) -- still bounded because each
        # highlight is its own ffmpeg re-encode, a real per-clip cost.
        validators=[MinValueValidator(1), MaxValueValidator(30)],
        help_text="How many highlight moments to ask the AI for.",
    )
    ai_creativity_level = models.CharField(
        max_length=16, choices=AiCreativityLevel.choices, default=AiCreativityLevel.BALANCED
    )

    # --- Inert until phase 3 (rendering) reads them ---
    export_mode = models.CharField(
        max_length=16,
        choices=ExportMode.choices,
        default=ExportMode.HIGHLIGHT_REEL,
        help_text="Highlight reel: a subset of AI-picked moments, fit to "
        "output_duration_seconds. Full video: the entire source, in order, "
        "with the same captions/B-roll/logo/music polish -- "
        "output_duration_seconds and num_highlights are unused in this mode.",
    )
    output_duration_seconds = models.PositiveSmallIntegerField(
        default=60,
        # No max: relies on PositiveSmallIntegerField's own ~32767s
        # ceiling as the only remaining sanity bound. A short-form-only
        # cap here would work against export_mode=full_video's whole
        # point (see also num_highlights above).
        validators=[MinValueValidator(15)],
    )
    aspect_ratio = models.CharField(
        max_length=8, choices=AspectRatio.choices, default=AspectRatio.VERTICAL
    )
    caption_style = models.CharField(
        max_length=16, choices=CaptionStyle.choices, default=CaptionStyle.BOLD
    )
    font = models.CharField(max_length=16, choices=FontChoice.choices, default=FontChoice.INTER)
    color_theme = models.CharField(
        max_length=16, choices=ColorTheme.choices, default=ColorTheme.DEFAULT
    )
    transition_style = models.CharField(
        max_length=16, choices=TransitionStyle.choices, default=TransitionStyle.FADE
    )
    music_style = models.CharField(
        max_length=16, choices=MusicStyle.choices, default=MusicStyle.NONE
    )
    subtitle_language = models.CharField(
        max_length=8,
        default="auto",
        help_text="ISO 639-1 code, 'auto' to match the detected transcript language, or 'none'.",
    )
    voice_over_style = models.CharField(
        max_length=16, choices=VoiceOverStyle.choices, default=VoiceOverStyle.NONE
    )
    broll_type = models.CharField(max_length=16, choices=BrollType.choices, default=BrollType.NONE)
    image_generation_enabled = models.BooleanField(default=False)
    internet_media_search_enabled = models.BooleanField(default=False)
    video_quality = models.CharField(
        max_length=8, choices=VideoQuality.choices, default=VideoQuality.Q_1080P
    )
    export_format = models.CharField(
        max_length=8, choices=ExportFormat.choices, default=ExportFormat.MP4
    )
    logo_image = models.ImageField(
        upload_to=upload_logo_path,
        null=True,
        blank=True,
        max_length=512,
        help_text="Optional watermark, composited in a fixed corner for the "
        "whole render. Presence of a file is what enables it -- no separate toggle.",
    )
    logo_position = models.CharField(
        max_length=16,
        choices=LogoPosition.choices,
        default=LogoPosition.BOTTOM_RIGHT,
        help_text="Where the logo/watermark sits — always scaled down to a small "
        "corner mark, never covering the video.",
    )

    class Meta:
        db_table = "export_settings"
        ordering = ["-created_at"]
        verbose_name_plural = "export settings"

    def __str__(self) -> str:
        return f"ExportSettings<{self.video_id}>"

    @property
    def temperature(self) -> float:
        return self.CREATIVITY_TEMPERATURE_MAP[self.ai_creativity_level]
