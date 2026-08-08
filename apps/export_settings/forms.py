from django import forms

from apps.export_settings.models import ExportSettings


class ExportSettingsForm(forms.ModelForm):
    class Meta:
        model = ExportSettings
        exclude = ["video"]  # noqa: DJ006 — explicit exclude reads clearer than listing 15 fields
