# AI Pipeline

## Capabilities and current implementations

| Capability | Interface | Default (local) | Alternative | Status |
|---|---|---|---|---|
| Speech-to-text | `domain.transcription.base.SpeechToTextProvider` | `faster_whisper` | — | phase 1 |
| Summarization / highlight extraction | `domain.ai.base.LLMProvider` | `ollama` | `openrouter` | phase 1 |
| Image generation | `domain.ai.base.ImageGenProvider` | — | — | interface only, no implementation (roadmap) |

Provider *selection* is env-driven and resolved by `domain/ai/registry.py`:

```bash
AI_STT_PROVIDER=faster_whisper
AI_LLM_PROVIDER=ollama       # or: openrouter
```

`apps.ai_providers.AIProviderConfig` is an admin-visible catalog of known
providers (for operator visibility/audit) — it does **not** drive selection
in phase 1. That's a documented future extension point, not a gap: adding a
DB-driven override means checking `AIProviderConfig` before falling back to
the env default inside `registry.py`, without any schema change.

## Why these defaults

- **faster-whisper over `openai-whisper`**: a CTranslate2 reimplementation
  of Whisper — noticeably faster on CPU-only dev machines with `int8`
  quantization, which matters for a local-first project where many
  contributors won't have a GPU. `WHISPER_MODEL_SIZE=small` is the default
  trade-off between speed and transcript quality; drop to `base`/`tiny` for
  faster CPU iteration, or set `WHISPER_DEVICE=cuda` if you have a GPU.
- **Ollama over a hosted API by default**: zero marginal cost per video, no
  API key required to get started, keeps the whole pipeline runnable
  offline. `OLLAMA_MODEL=qwen2.5:3b` is a small, CPU-friendly default that
  reliably follows the strict-JSON instructions this pipeline depends on;
  larger local models (7B+) will generally produce better
  summaries/highlights if you have the RAM/compute.
- **OpenRouter as the pluggable alternative**: one env var away
  (`AI_LLM_PROVIDER=openrouter` + `OPENROUTER_API_KEY`) when you want a
  stronger hosted model instead of local inference.

## The highlight-extraction prompt contract

`domain/ai/prompts/highlight_extraction.py` owns the prompt template and
response schema shared by **every** `LLMProvider` implementation, so
Ollama and OpenRouter parse identically:

1. `build_prompt()` — assembles the timestamped transcript, scene
   boundaries, and video duration into a single prompt instructing the
   model to return one JSON object (summary, suggested title/description/
   hashtags, ranked highlights with rationale).
2. `parse_analysis_response()` — extracts the first `{...}` block from the
   raw completion (tolerates markdown fences / stray commentary) and
   validates it against `AnalysisSchema` (Pydantic).
3. `generate_analysis_with_repair()` — the shared retry flow every provider
   calls: send the prompt, try to parse; on failure, send exactly one
   repair message ("your last response wasn't valid JSON, try again") and
   parse the retry. A second failure raises
   `domain.exceptions.ProviderResponseParseError` (a `PermanentPipelineError`
   — no further retries; see `apps/highlights/tasks.py`).

This shared flow is why adding a new *LLM* provider is small: you only
implement the HTTP transport (`_send_chat`), not prompt construction or
response validation.

## Adding a new provider

**New LLM provider** (e.g. a different hosted API, or `vllm`/`llama.cpp`
server):

1. Create `domain/ai/providers/your_provider.py` implementing
   `LLMProvider.generate_analysis()`. In the common case, this is a
   one-line call to `domain.ai.prompts.highlight_extraction.generate_analysis_with_repair()`
   passing a `send_chat(messages) -> str` closure that does your HTTP call —
   see `ollama_provider.py` for the pattern.
2. Register it in `domain/ai/registry.py::LLM_PROVIDERS`.
3. Add its config keys to `.env.example` and
   `AI_LLM_PROVIDER_KWARGS` in `config/settings/base.py`.
4. Add unit tests mirroring `domain/tests/test_ollama_provider.py`
   (mock `httpx.post`, assert the transient/permanent error mapping).

**New STT provider**: same shape, implementing
`SpeechToTextProvider.transcribe()`, registered in `STT_PROVIDERS`.

**Image generation** (Stable Diffusion/Flux, etc.): the `ImageGenProvider`
ABC already exists in `domain/ai/base.py` — implementing it, wiring a
registry, a Celery task, and a model to store generated assets is tracked
in [docs/roadmap.md](roadmap.md); it's intentionally out of scope for
phase 1.

## Scene detection is not (yet) pluggable

Unlike STT/LLM, `domain/scene_detection/providers/pyscenedetect_provider.py`
is instantiated directly in `apps/scenes/tasks.py` rather than through a
registry — there's only one implementation today. If/when a second
backend appears, promoting it to a registry-based capability (mirroring
`STT_PROVIDERS`/`LLM_PROVIDERS`) is a small, mechanical change.

## Operational notes

- `CELERY_TASK_ALWAYS_EAGER=true` is useful for a quick worker-less local
  check, but a permanent pipeline failure will raise synchronously inside
  the web request instead of just marking the video `FAILED` — see
  [docs/architecture.md](architecture.md#task-graph). Never enable it in
  production.
- `make ollama-pull` is a separate step from `make up` on purpose — the
  model isn't pulled automatically on container start, to avoid a surprise
  multi-gigabyte download on first boot.
- **Ollama timeouts on CPU-only hardware**: `OLLAMA_TIMEOUT` defaults to
  300s. The first request after the container starts also pays for
  loading the model's weights into RAM (Ollama keeps it loaded afterward,
  so subsequent requests are faster), and a several-minute video produces
  a large transcript to prefill — both add up on CPU-only inference. If
  `docker compose logs worker` shows `Ollama request timed out` on the
  analysis step, raise `OLLAMA_TIMEOUT` further in `.env` (no rebuild
  needed, just `docker compose up -d web worker`), or switch to a smaller
  model (`OLLAMA_MODEL=qwen2.5:1.5b` or similar) if your hardware is
  consistently too slow for the 3B default. A 404 on the other hand (model
  never pulled) now fails immediately rather than retrying — see
  `domain/ai/providers/http_utils.py`.
