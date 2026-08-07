"""Celery application instance for the `reeler` project.

Autodiscovers `tasks.py` in every installed app, so each app's Celery tasks
(apps/videos/tasks.py, apps/transcripts/tasks.py, ...) are picked up without
manual registration.
"""

import os

from celery import Celery

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.dev")

app = Celery("reeler")
app.config_from_object("django.conf:settings", namespace="CELERY")
app.autodiscover_tasks()
