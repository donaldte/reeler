from django.urls import path

from apps.renders import views

app_name = "renders"

urlpatterns = [
    path("<uuid:video_id>/render/", views.start_render_view, name="start"),
    path(
        "render-jobs/<uuid:render_job_id>/status-fragment/",
        views.render_status_fragment,
        name="status_fragment",
    ),
]
