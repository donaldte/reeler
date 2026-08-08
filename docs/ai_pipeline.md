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
   hashtags, ranked highlights with rationale, plus a suggested `emoji`
   and `cut`/`fade` `transition` per highlight). The schema example shown
   to the model contains **two** highlight objects, not one — a
   single-item example array turned out to be a plausible reason smaller
   local models under-delivered on `num_highlights` (observed in
   production: 3 requested, 1 returned), likely pattern-matching the
   example's length rather than treating it as a repeatable schema. The
   instruction text is also unhedged ("Identify EXACTLY N", not "up to
   N").
2. `parse_analysis_response()` — extracts the first `{...}` block from the
   raw completion (tolerates markdown fences / stray commentary) and
   validates it against `AnalysisSchema` (Pydantic).
3. `generate_analysis_with_repair()` — the shared retry flow every provider
   calls: send the prompt, try to parse. One repair round happens if
   either (a) the response wasn't valid JSON, or (b) it parsed fine but
   came back with fewer highlights than `num_highlights` — using a
   count-specific repair message in the second case, a generic
   JSON-repair message in the first. A short-but-valid first result is
   never discarded: if the repair round fails to parse, or comes back
   even shorter, the original result is kept rather than losing a usable
   analysis over an imperfect count. A first response that never parsed
   at all, with a repair that also fails to parse, is the only case that
   raises `domain.exceptions.ProviderResponseParseError` (a
   `PermanentPipelineError` — no further retries; see
   `apps/highlights/tasks.py`).

This shared flow is why adding a new *LLM* provider is small: you only
implement the HTTP transport (`_send_chat`), not prompt construction or
response validation.

## Adding a new provider

**New LLM provider** (e.g. a different hosted API, or `vllm`/`llama.cpp`
server):

1. Create `domain/ai/providers/your_provider.py` implementing
   `LLMProvider.generate_analysis()`, including its `num_highlights` and
   `temperature` kwargs (both user-configurable per-video via
   `apps.export_settings.models.ExportSettings` — see `docs/architecture.md`).
   In the common case this is a one-line call to
   `domain.ai.prompts.highlight_extraction.generate_analysis_with_repair()`
   passing a `send_chat(messages) -> str` closure that does your HTTP call
   (capture `temperature` in the closure, since `send_chat` itself only
   takes `messages`) — see `ollama_provider.py` for the pattern. Ignoring
   `temperature` if your backend has no equivalent is fine; ignoring
   `num_highlights` is not, since it changes what the prompt itself asks for.
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
  600s. Measured directly against `qwen2.5:3b` on modest CPU-only hardware
  (a laptop, no GPU): a 1638-token prompt took 85s to *prefill* (~19
  tokens/sec) but generation ran at only ~3-4 tokens/sec — a 17-token reply
  took 5s on its own. The takeaway: **generation speed, not prompt size, is
  usually the dominant cost.** Our analysis response (title, description,
  hashtags, several highlights with rationale) is a few hundred output
  tokens, which at ~3-4 tokens/sec alone can take 2+ minutes — on top of
  prefill, on top of a multi-second cold model load if it had gone idle.
  `DEFAULT_NUM_HIGHLIGHTS` (3) and `MAX_TRANSCRIPT_CHARS_IN_PROMPT` (6000,
  in `domain/ai/prompts/highlight_extraction.py`) are both tuned with this
  in mind — fewer requested highlights means less output to generate. If
  `docker compose logs worker` still shows `Ollama request timed out` on
  the analysis step:
  1. Raise `OLLAMA_TIMEOUT` further in `.env` (no rebuild needed, just
     `docker compose up -d web worker`).
  2. Switch to a smaller/faster model — `OLLAMA_MODEL=qwen2.5:1.5b` or
     `qwen2.5:0.5b` trade some quality for meaningfully faster CPU
     inference, especially on generation-bound requests like this one.
  3. To directly measure your own hardware's prefill/generation speed
     (rather than guessing), POST a large prompt straight to Ollama and
     read `prompt_eval_count`/`prompt_eval_duration`/`eval_count`/
     `eval_duration` from its JSON response.

  A 404 (model never pulled), on the other hand, now fails immediately
  rather than retrying — see `domain/ai/providers/http_utils.py`.
- **Word-level timestamps are off** (`FasterWhisperProvider`'s
  `word_timestamps=False`) — segment-level timestamps are enough for
  scene-aligned highlight extraction, but it's the reason
  `domain/rendering/captions.py`'s `caption_style="karaoke"` currently
  falls back to the same styling as `"bold"` rather than true word-by-word
  highlighting. Flipping this on (and threading the finer-grained timing
  through `TranscriptSegment`) is the concrete next step for that —
  tracked in [docs/roadmap.md](roadmap.md).
