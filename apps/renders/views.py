from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.http import require_POST

from apps.common.http import AuthenticatedHttpRequest
from apps.renders.models import RenderJob
from apps.renders.services import create_render_job
from apps.videos.models import UploadedVideo


@login_required
@require_POST
def start_render_view(request: AuthenticatedHttpRequest, video_id: str) -> HttpResponse:
    """Kicks off a render for `video_id` and redirects back to the video
    detail page — no separate GET page, same POST-only pattern as
    apps.export_settings.views.save_export_settings_view.
    """
    video = get_object_or_404(UploadedVideo, pk=video_id, project__owner=request.user)
    try:
        create_render_job(video)
    except ValueError as exc:
        messages.error(request, str(exc))
    else:
        messages.success(request, "Render started.")
    return redirect(reverse("videos:detail", args=[video.id]))


@login_required
def render_status_fragment(request: AuthenticatedHttpRequest, render_job_id: str) -> HttpResponse:
    render_job = get_object_or_404(
        RenderJob.objects.select_related("video"),
        pk=render_job_id,
        video__project__owner=request.user,
    )
    return render(request, "renders/_status_fragment.html", {"render_job": render_job})
