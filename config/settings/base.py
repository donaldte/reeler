"""Base Django settings for Reeler, shared by all environments.

Configuration follows the 12-factor pattern: everything environment-specific
is read from `.env` via django-environ. See `.env.example` for the full list
of supported variables.
"""

from pathlib import Path

import environ

BASE_DIR = Path(__file__).resolve().parent.parent.parent

env = environ.Env()
environ.Env.read_env(str(BASE_DIR / ".env"))

SECRET_KEY = env.str("DJANGO_SECRET_KEY", default="insecure-dev-key-change-me")
DEBUG = env.bool("DJANGO_DEBUG", default=False)
ALLOWED_HOSTS = env.list("DJANGO_ALLOWED_HOSTS", default=["localhost", "127.0.0.1"])

# ---------------------------------------------------------------------------
# Applications
# ---------------------------------------------------------------------------
DJANGO_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
]

THIRD_PARTY_APPS = [
    "rest_framework",
    "drf_spectacular",
    "django_htmx",
]

LOCAL_APPS = [
    "apps.accounts",
    "apps.common",
    "apps.videos",
    "apps.transcripts",
    "apps.scenes",
    "apps.highlights",
    "apps.export_settings",
    "apps.renders",
    "apps.ai_providers",
]

INSTALLED_APPS = DJANGO_APPS + THIRD_PARTY_APPS + LOCAL_APPS

AUTH_USER_MODEL = "accounts.User"

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "django_htmx.middleware.HtmxMiddleware",
]

ROOT_URLCONF = "config.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"
ASGI_APPLICATION = "config.asgi.application"

# ---------------------------------------------------------------------------
# Database — PostgreSQL only, no SQLite fallback (dev must match prod).
# ---------------------------------------------------------------------------
DATABASES = {
    "default": env.db_url(
        "DATABASE_URL",
        default="postgres://reeler:reeler@localhost:5432/reeler",
    ),
}
DATABASES["default"]["ATOMIC_REQUESTS"] = True

# ---------------------------------------------------------------------------
# Password validation
# ---------------------------------------------------------------------------
AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

# ---------------------------------------------------------------------------
# Internationalization
# ---------------------------------------------------------------------------
LANGUAGE_CODE = "en-us"
TIME_ZONE = "UTC"
USE_I18N = True
USE_TZ = True

# ---------------------------------------------------------------------------
# Static / media
# ---------------------------------------------------------------------------
STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
STATICFILES_DIRS = [BASE_DIR / "static"]
STATICFILES_STORAGE = "whitenoise.storage.CompressedManifestStaticFilesStorage"

MEDIA_URL = "media/"
MEDIA_ROOT = BASE_DIR / "media"

# Uploaded video size guardrails (bytes) — enforced in apps.videos forms/serializers.
MAX_UPLOAD_SIZE_BYTES = env.int("MAX_UPLOAD_SIZE_BYTES", default=1024 * 1024 * 1024)  # 1 GB

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# ---------------------------------------------------------------------------
# REST framework / API schema
# ---------------------------------------------------------------------------
REST_FRAMEWORK = {
    "DEFAULT_SCHEMA_CLASS": "drf_spectacular.openapi.AutoSchema",
    "DEFAULT_PAGINATION_CLASS": "apps.common.pagination.DefaultPagination",
    "PAGE_SIZE": 20,
    "EXCEPTION_HANDLER": "apps.common.exceptions.reeler_exception_handler",
    "DEFAULT_AUTHENTICATION_CLASSES": [
        "rest_framework.authentication.SessionAuthentication",
    ],
}

SPECTACULAR_SETTINGS = {
    "TITLE": "Reeler API",
    "DESCRIPTION": "AI-powered short-video editor — upload, analysis, and (future) rendering.",
    "VERSION": "0.1.0",
    "SERVE_INCLUDE_SCHEMA": False,
}

# ---------------------------------------------------------------------------
# Celery
# ---------------------------------------------------------------------------
CELERY_BROKER_URL = env.str("CELERY_BROKER_URL", default="redis://localhost:6379/0")
CELERY_RESULT_BACKEND = env.str("CELERY_RESULT_BACKEND", default="redis://localhost:6379/1")
CELERY_ACCEPT_CONTENT = ["json"]
CELERY_TASK_SERIALIZER = "json"
CELERY_RESULT_SERIALIZER = "json"
CELERY_TASK_TRACK_STARTED = True
CELERY_WORKER_PREFETCH_MULTIPLIER = 1
CELERY_TASK_SOFT_TIME_LIMIT = env.int("CELERY_TASK_SOFT_TIME_LIMIT", default=1800)
CELERY_TASK_TIME_LIMIT = env.int("CELERY_TASK_TIME_LIMIT", default=1900)
CELERY_TASK_ALWAYS_EAGER = env.bool("CELERY_TASK_ALWAYS_EAGER", default=False)
CELERY_TASK_EAGER_PROPAGATES = True

# ---------------------------------------------------------------------------
# AI provider selection — env-driven, resolved by domain.ai.registry.
# See docs/ai_pipeline.md for how to add a new provider.
# ---------------------------------------------------------------------------
AI_STT_PROVIDER = env.str("AI_STT_PROVIDER", default="faster_whisper")
AI_STT_PROVIDER_KWARGS = {
    "faster_whisper": {
        "model_size": env.str("WHISPER_MODEL_SIZE", default="small"),
        "device": env.str("WHISPER_DEVICE", default="cpu"),
        "compute_type": env.str("WHISPER_COMPUTE_TYPE", default="int8"),
    },
}

AI_LLM_PROVIDER = env.str("AI_LLM_PROVIDER", default="ollama")
AI_LLM_PROVIDER_KWARGS = {
    "ollama": {
        "base_url": env.str("OLLAMA_BASE_URL", default="http://localhost:11434"),
        "model": env.str("OLLAMA_MODEL", default="qwen2.5:3b"),
        # Measured on real CPU-only hardware: generating the structured JSON
        # analysis response runs at only ~3-4 tokens/sec (far slower than
        # prefill) -- a few hundred output tokens alone can take 2+ minutes,
        # on top of prefill and (if the model was idle) a multi-second cold
        # load. 600s gives real headroom. Confirmed in practice — see
        # docs/ai_pipeline.md#operational-notes.
        "timeout": env.float("OLLAMA_TIMEOUT", default=600.0),
    },
    "openrouter": {
        "api_key": env.str("OPENROUTER_API_KEY", default=""),
        "model": env.str("OPENROUTER_MODEL", default="meta-llama/llama-3.1-8b-instruct:free"),
        "base_url": env.str("OPENROUTER_BASE_URL", default="https://openrouter.ai/api/v1"),
        "timeout": env.float("OPENROUTER_TIMEOUT", default=120.0),
    },
}

SCENE_DETECTION_THRESHOLD = env.float("SCENE_DETECTION_THRESHOLD", default=27.0)
SCENE_DETECTION_MIN_SCENE_LEN_SECONDS = env.float(
    "SCENE_DETECTION_MIN_SCENE_LEN_SECONDS", default=0.6
)

# ---------------------------------------------------------------------------
# Logging — structured, environment-overridable level.
# ---------------------------------------------------------------------------
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "verbose": {
            "format": "%(asctime)s %(levelname)-8s %(name)s %(module)s: %(message)s",
        },
    },
    "handlers": {
        "console": {"class": "logging.StreamHandler", "formatter": "verbose"},
    },
    "root": {"handlers": ["console"], "level": env.str("LOG_LEVEL", default="INFO")},
    "loggers": {
        "django": {
            "handlers": ["console"],
            "level": env.str("LOG_LEVEL", default="INFO"),
            "propagate": False,
        },
        "celery": {
            "handlers": ["console"],
            "level": env.str("LOG_LEVEL", default="INFO"),
            "propagate": False,
        },
        "reeler": {
            "handlers": ["console"],
            "level": env.str("LOG_LEVEL", default="DEBUG"),
            "propagate": False,
        },
    },
}
