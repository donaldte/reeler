"""Orchestration glue for apps.export_settings — analogous to
apps.videos.services, this is the only place ExportSettings gets
created/updated and the only place that decides whether a settings change
should re-run the analysis step.
"""

from apps.export_settings.models import ExportSettings
from apps.videos.models import UploadedVideo

# The only fields that actually change LLM behavior today — see
# apps/highlights/tasks.py::generate_analysis_task. Every other
# ExportSettings field is stored for phase 3 (rendering) to read later.
ANALYSIS_AFFECTING_FIELDS = {"num_highlights", "ai_creativity_level"}


def get_or_create_export_settings(video: UploadedVideo) -> ExportSettings:
    """Returns the video's most recent settings row, creating a
    default-valued one if none exists yet. Called both by the settings
    form/API (to pre-populate) and by generate_analysis_task (so even the
    very first automatic analysis run right after upload uses persisted
    defaults rather than a hardcoded constant).
    """
    settings_obj = ExportSettings.objects.filter(video=video).order_by("-created_at").first()
    if settings_obj is not None:
        return settings_obj
    return ExportSettings.objects.create(video=video)


def maybe_rerun_analysis(video: UploadedVideo, changed_fields: set[str]) -> bool:
    """Re-runs just the LLM analysis step if a field that actually affects
    it changed, and the video has already completed at least one analysis
    pass. If the video hasn't gotten there yet, the just-saved settings
    will be picked up naturally when it does — no rerun needed.

    Shared by the Django form view (`form.changed_data`) and the DRF view
    (a manual diff against `serializer.validated_data`).
    """
    should_rerun = (
        bool(changed_fields & ANALYSIS_AFFECTING_FIELDS)
        and video.status == UploadedVideo.Status.COMPLETED
    )

    if should_rerun:
        from apps.videos.tasks import rerun_analysis_only  # avoids a module-load cycle

        rerun_analysis_only(str(video.id))

    return should_rerun
