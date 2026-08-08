from django.contrib.auth.decorators import login_required
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse

from apps.common.http import AuthenticatedHttpRequest
from apps.export_settings.forms import ExportSettingsForm
from apps.export_settings.services import get_or_create_export_settings
from apps.videos.forms import VideoUploadForm
from apps.videos.models import UploadedVideo
from apps.videos.services import create_video_and_launch_pipeline


@login_required
def upload_video(request: AuthenticatedHttpRequest) -> HttpResponse:
    if request.method == "POST":
        form = VideoUploadForm(request.POST, request.FILES)
        if form.is_valid():
            video = create_video_and_launch_pipeline(
                owner=request.user, uploaded_file=form.cleaned_data["file"]
            )
            return redirect(reverse("videos:detail", args=[video.id]))
    else:
        form = VideoUploadForm()

    recent_videos = (
        UploadedVideo.objects.filter(project__owner=request.user)
        .select_related("project")
        .order_by("-created_at")[:20]
    )
    return render(request, "videos/upload.html", {"form": form, "recent_videos": recent_videos})


@login_required
def video_detail(request: AuthenticatedHttpRequest, pk: str) -> HttpResponse:
    video = get_object_or_404(
        UploadedVideo.objects.select_related("project"), pk=pk, project__owner=request.user
    )
    # The one place a view reaches across app boundaries at the Python
    # level (not just via template {% include %} like the read-only
    # transcript/scenes/analysis partials below) — a bound form can't be
    # built purely from a reverse-relation lookup in a template. See
    # docs/architecture.md.
    export_settings_form = ExportSettingsForm(instance=get_or_create_export_settings(video))
    return render(
        request,
        "videos/detail.html",
        {"video": video, "export_settings_form": export_settings_form},
    )


@login_required
def video_status_fragment(request: AuthenticatedHttpRequest, pk: str) -> HttpResponse:
    video = get_object_or_404(UploadedVideo, pk=pk, project__owner=request.user)
    return render(request, "videos/_status_fragment.html", {"video": video})
