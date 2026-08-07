"""Settings used by pytest / CI.

Runs Celery tasks synchronously (no worker/broker needed) and uses fast
password hashing to keep the test suite quick.
"""

from .base import *  # noqa: F403
from .base import BASE_DIR, env

DEBUG = False
SECRET_KEY = "test-secret-key-not-for-production"
ALLOWED_HOSTS = ["*"]

DATABASES["default"] = env.db_url(  # noqa: F405
    "DATABASE_URL",
    default="postgres://reeler:reeler@localhost:5432/reeler_test",
)

CELERY_TASK_ALWAYS_EAGER = True
CELERY_TASK_EAGER_PROPAGATES = True
CELERY_BROKER_URL = "memory://"

PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]

MEDIA_ROOT = BASE_DIR / "tests" / "tmp_media"

# Never hit real network AI providers in tests — every test that exercises
# the pipeline must mock domain.ai.registry.get_stt_provider / get_llm_provider.
AI_STT_PROVIDER = "faster_whisper"
AI_LLM_PROVIDER = "ollama"
