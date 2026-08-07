import uuid

from django.db import models


class TimeStampedModel(models.Model):
    """Abstract base model shared by every domain entity in the platform.

    Uses a UUID primary key (safe to expose in API responses/URLs without
    leaking row counts) plus created/updated timestamps.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True
        ordering = ["-created_at"]
