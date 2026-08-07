from django.contrib.auth.decorators import login_required
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse

from apps.common.http import AuthenticatedHttpRequest
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
    return render(request, "videos/detail.html", {"video": video})


@login_required
def video_status_fragment(request: AuthenticatedHttpRequest, pk: str) -> HttpResponse:
    video = get_object_or_404(UploadedVideo, pk=pk, project__owner=request.user)
    return render(request, "videos/_status_fragment.html", {"video": video})
