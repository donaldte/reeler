"""Local development settings."""

from .base import *  # noqa: F403
from .base import env

DEBUG = True
ALLOWED_HOSTS = ["*"]

SECRET_KEY = env.str("DJANGO_SECRET_KEY", default="insecure-dev-key-change-me")

# Show full tracebacks for API errors during development.
REST_FRAMEWORK = {
    **REST_FRAMEWORK,  # noqa: F405
    "DEFAULT_AUTHENTICATION_CLASSES": [
        "rest_framework.authentication.SessionAuthentication",
    ],
}

INTERNAL_IPS = ["127.0.0.1"]
