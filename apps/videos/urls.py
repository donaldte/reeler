from django.urls import path

from apps.videos import views

app_name = "videos"

urlpatterns = [
    path("", views.upload_video, name="upload"),
    path("<uuid:pk>/", views.video_detail, name="detail"),
    path("<uuid:pk>/status-fragment/", views.video_status_fragment, name="status_fragment"),
]
