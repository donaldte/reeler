from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse
from django.views.decorators.http import require_POST

from apps.common.http import AuthenticatedHttpRequest
from apps.export_settings.forms import ExportSettingsForm
from apps.export_settings.services import get_or_create_export_settings, maybe_rerun_analysis
from apps.videos.models import UploadedVideo


@login_required
@require_POST
def save_export_settings_view(request: AuthenticatedHttpRequest, video_id: str) -> HttpResponse:
    """Saves the customization panel embedded in `videos/detail.html`
    (see apps/videos/views.py::video_detail) and redirects back there.

    No separate GET page — the form is only ever rendered inline on the
    video detail page, so this endpoint is POST-only.
    """
    video = get_object_or_404(UploadedVideo, pk=video_id, project__owner=request.user)
    settings_obj = get_or_create_export_settings(video)
    form = ExportSettingsForm(request.POST, request.FILES, instance=settings_obj)

    if form.is_valid():
        changed_fields = set(form.changed_data)
        form.save()
        did_rerun = maybe_rerun_analysis(video, changed_fields)
        if did_rerun:
            messages.success(
                request, "Settings saved — re-running analysis with your new preferences."
            )
        else:
            messages.success(request, "Settings saved.")
    else:
        # All fields are either bounded numeric inputs or fixed <select>
        # choices, so an invalid submission through the normal UI is rare
        # (mainly reachable via direct form tampering) — a flash message is
        # enough here rather than re-rendering the whole detail page with
        # the invalid bound form.
        error_text = "; ".join(
            f"{field}: {', '.join(str(e) for e in errs)}" for field, errs in form.errors.items()
        )
        messages.error(request, f"Couldn't save settings — {error_text}")

    return redirect(reverse("videos:detail", args=[video.id]))
