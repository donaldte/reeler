from django.db import models

from apps.common.models import TimeStampedModel


class AIProviderConfig(TimeStampedModel):
    """Admin-visible catalog of known AI providers per capability.

    Provider *selection* in phase 1 is env-driven (AI_STT_PROVIDER /
    AI_LLM_PROVIDER, resolved by domain.ai.registry) — this table does not
    drive that selection yet. It exists so operators have a place to see
    what's available/active and to audit configuration, and as the landing
    spot for a future DB-driven override layer (checked after the env
    default) without a disruptive schema change. Never store secrets here —
    `extra_config` is for non-secret settings only (API keys stay in env).
    """

    class Capability(models.TextChoices):
        STT = "stt", "Speech-to-text"
        LLM = "llm", "Large language model"
        IMAGE_GEN = "image_gen", "Image generation"

    capability = models.CharField(max_length=32, choices=Capability.choices)
    provider_key = models.CharField(
        max_length=64, help_text="Registry key, e.g. 'ollama' — must match domain.ai.registry."
    )
    display_name = models.CharField(max_length=128)
    is_active = models.BooleanField(default=True)
    priority = models.PositiveSmallIntegerField(
        default=0, help_text="Lower runs first when multiple are active."
    )
    extra_config = models.JSONField(
        default=dict, blank=True, help_text="Non-secret config only — no API keys."
    )

    class Meta:
        db_table = "ai_providers_config"
        ordering = ["capability", "priority"]
        constraints = [
            models.UniqueConstraint(
                fields=["capability", "provider_key"], name="unique_provider_per_capability"
            )
        ]

    def __str__(self) -> str:
        return f"{self.get_capability_display()}: {self.display_name}"
