"""Shared LLM-generation defaults.

Split into its own module (rather than living in `base.py` or
`prompts/highlight_extraction.py`) because both of those import from each
other in different directions — `prompts` imports `AnalysisDTO`/
`HighlightDTO` from `base`, and `base`'s `LLMProvider.generate_analysis`
signature needs these defaults too. A standalone module with no
dependencies on either avoids the cycle.
"""

# Measured on real CPU-only hardware (see docs/ai_pipeline.md#operational-notes):
# a 1638-token prompt took 85s to prefill but only generated 17 output
# tokens in 5s -- generation ran at ~3.4 tokens/sec, far slower than
# prefill's ~19 tokens/sec. Our real analysis response (title, description,
# hashtags, several highlights with rationale) is a few hundred output
# tokens, not 17 -- generation time, not prompt size, is the dominant cost.
# Fewer requested highlights means less output to generate. Overridable
# per-video via apps.export_settings.models.ExportSettings.num_highlights.
DEFAULT_NUM_HIGHLIGHTS = 3

# Default LLM sampling temperature when no ExportSettings-derived value is
# given (e.g. a caller using a provider directly, outside the Celery
# pipeline). apps.export_settings.models.ExportSettings.temperature maps
# its user-facing "creativity level" to a value in this same range.
DEFAULT_TEMPERATURE = 0.5
