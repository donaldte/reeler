from django.urls import path

from apps.export_settings import views

app_name = "export_settings"

urlpatterns = [
    path("<uuid:video_id>/settings/", views.save_export_settings_view, name="save"),
]
