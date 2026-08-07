from django.contrib import admin

from .models import Scene


@admin.register(Scene)
class SceneAdmin(admin.ModelAdmin):
    list_display = ("video", "index", "start_time", "end_time")
    list_filter = ("video",)
