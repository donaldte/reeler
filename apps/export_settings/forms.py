from django import forms
from django.conf import settings as django_settings

from apps.export_settings.models import ExportSettings

# Mirrors apps.videos.forms.VideoUploadForm's ALLOWED_VIDEO_EXTENSIONS /
# clean_file pattern exactly, for the same reason: a logo is a tiny image,
# not a multi-GB video, so a smaller dedicated size cap
# (MAX_LOGO_UPLOAD_SIZE_BYTES) makes more sense than reusing
# MAX_UPLOAD_SIZE_BYTES.
ALLOWED_LOGO_EXTENSIONS = {".png", ".jpg", ".jpeg"}


class ExportSettingsForm(forms.ModelForm):
    class Meta:
        model = ExportSettings
        exclude = ["video"]  # noqa: DJ006 — explicit exclude reads clearer than listing 15 fields

    def clean_logo_image(self) -> forms.ImageField | None:
        uploaded = self.cleaned_data.get("logo_image")
        # An ImageField's cleaned_data is the *new* upload only when one was
        # submitted this request -- unchanged (already-set-and-kept) or
        # never-set cases return the existing FieldFile / None, neither of
        # which is a fresh UploadedFile, so skip validation for those.
        if not uploaded or not hasattr(uploaded, "size"):
            return uploaded

        extension = "." + uploaded.name.rsplit(".", 1)[-1].lower() if "." in uploaded.name else ""
        if extension not in ALLOWED_LOGO_EXTENSIONS:
            allowed = ", ".join(sorted(ALLOWED_LOGO_EXTENSIONS))
            raise forms.ValidationError(f"Unsupported file type {extension!r}. Allowed: {allowed}")

        if uploaded.size > django_settings.MAX_LOGO_UPLOAD_SIZE_BYTES:
            max_mb = django_settings.MAX_LOGO_UPLOAD_SIZE_BYTES // (1024 * 1024)
            raise forms.ValidationError(f"File too large. Maximum size is {max_mb} MB.")

        return uploaded
