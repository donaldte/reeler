from django.contrib import admin

from .models import AIProviderConfig


@admin.register(AIProviderConfig)
class AIProviderConfigAdmin(admin.ModelAdmin):
    list_display = ("capability", "provider_key", "display_name", "is_active", "priority")
    list_filter = ("capability", "is_active")
