from django import forms
from django.conf import settings
from django.core.files.uploadedfile import UploadedFile

ALLOWED_VIDEO_EXTENSIONS = {".mp4", ".mov", ".mkv", ".webm", ".avi"}


class VideoUploadForm(forms.Form):
    file = forms.FileField(help_text="MP4, MOV, MKV, WebM, or AVI.")

    def clean_file(self) -> UploadedFile:
        uploaded = self.cleaned_data["file"]

        extension = "." + uploaded.name.rsplit(".", 1)[-1].lower() if "." in uploaded.name else ""
        if extension not in ALLOWED_VIDEO_EXTENSIONS:
            allowed = ", ".join(sorted(ALLOWED_VIDEO_EXTENSIONS))
            raise forms.ValidationError(f"Unsupported file type {extension!r}. Allowed: {allowed}")

        if uploaded.size > settings.MAX_UPLOAD_SIZE_BYTES:
            max_mb = settings.MAX_UPLOAD_SIZE_BYTES // (1024 * 1024)
            raise forms.ValidationError(f"File too large. Maximum size is {max_mb} MB.")

        return uploaded
