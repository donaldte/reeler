"""Prompt template + strict-JSON response schema shared by every LLMProvider
implementation, so Ollama and OpenRouter parse/validate identically.
"""

import json
import re
from collections.abc import Callable

from pydantic import BaseModel, ValidationError

from domain.ai.base import AnalysisDTO, HighlightDTO
from domain.exceptions import ProviderResponseParseError
from domain.scene_detection.base import SceneDTO
from domain.transcription.base import TranscriptionResult

ChatMessages = list[dict[str, str]]

# Measured on real CPU-only hardware (see docs/ai_pipeline.md#operational-notes):
# a 1638-token prompt took 85s to prefill but only generated 17 output
# tokens in 5s -- generation ran at ~3.4 tokens/sec, far slower than
# prefill's ~19 tokens/sec. Our real analysis response (title, description,
# hashtags, several highlights with rationale) is a few hundred output
# tokens, not 17 -- generation time, not prompt size, is the dominant cost.
# Fewer requested highlights means less output to generate.
DEFAULT_NUM_HIGHLIGHTS = 3

# Bounds how much transcript text goes into the prompt, independent of
# source video length. Confirmed in practice: an unbounded prompt for a
# several-minute video pushes CPU-only local inference (the local-first
# default) well past reasonable timeouts — prefill time scales with prompt
# size, and this project has no control over how long a user's source
# video is. ~6000 chars is roughly 1500-1700 tokens for typical prose,
# leaving more of the timeout budget for the (slower, per-token) generation
# phase above. See docs/ai_pipeline.md#operational-notes.
MAX_TRANSCRIPT_CHARS_IN_PROMPT = 6000

SYSTEM_PROMPT = (
    "You are a professional short-form video editor. Given a transcript and scene "
    "boundaries for a longer video, identify the most compelling, self-contained "
    "moments for a short (under 4 minute) social video, and produce metadata for "
    "publishing it. Respond with ONLY a single JSON object matching the schema you "
    "are given — no markdown fences, no commentary, no explanation before or after."
)

REPAIR_PROMPT = (
    "Your previous response could not be parsed as valid JSON matching the required "
    "schema. Respond again with ONLY the corrected JSON object — no markdown fences, "
    "no commentary."
)


class HighlightSchema(BaseModel):
    rank: int
    start: float
    end: float
    rationale: str
    score: float | None = None
    suggested_clip_title: str | None = None


class AnalysisSchema(BaseModel):
    summary: str
    suggested_title: str
    suggested_description: str
    suggested_hashtags: list[str]
    highlights: list[HighlightSchema]


def _transcript_lines_for_prompt(transcript: TranscriptionResult) -> tuple[str, bool]:
    """Renders each segment as `[start-end] text`, one per line, bounded by
    MAX_TRANSCRIPT_CHARS_IN_PROMPT.

    When the full transcript would exceed the budget, evenly downsamples
    segments across the *whole* video (keeping the first and last) rather
    than truncating the tail — a compelling highlight is just as likely
    near the end of a long video as the start, so losing temporal coverage
    would bias highlight extraction toward the beginning.

    Returns (rendered_text, was_downsampled) — callers use the flag to
    tell the model its view of the transcript is incomplete.
    """
    all_lines = [f"[{seg.start:.1f}-{seg.end:.1f}] {seg.text}" for seg in transcript.segments]
    full_text = "\n".join(all_lines)
    if len(full_text) <= MAX_TRANSCRIPT_CHARS_IN_PROMPT or len(all_lines) <= 1:
        return full_text, False

    avg_line_len = len(full_text) / len(all_lines)
    target_count = max(1, int(MAX_TRANSCRIPT_CHARS_IN_PROMPT / max(avg_line_len, 1)))
    step = max(1, len(all_lines) / target_count)
    sampled_indices = sorted({int(i * step) for i in range(target_count)} | {0, len(all_lines) - 1})
    sampled_lines = [all_lines[i] for i in sampled_indices if i < len(all_lines)]
    return "\n".join(sampled_lines), True


def build_prompt(
    *,
    transcript: TranscriptionResult,
    scenes: list[SceneDTO],
    video_duration: float,
    num_highlights: int = DEFAULT_NUM_HIGHLIGHTS,
) -> str:
    transcript_lines, was_downsampled = _transcript_lines_for_prompt(transcript)
    downsample_note = (
        "\n\n(Note: this transcript was downsampled for length — some segments were "
        "omitted, but coverage spans the full video duration.)"
        if was_downsampled
        else ""
    )
    scene_lines = "\n".join(f"Scene {s.index}: {s.start:.1f}-{s.end:.1f}s" for s in scenes)

    schema_example = {
        "summary": "2-4 sentence summary of the video content.",
        "suggested_title": "Punchy title under 100 characters.",
        "suggested_description": "1-2 sentence social media description.",
        "suggested_hashtags": ["#example", "#shortform"],
        "highlights": [
            {
                "rank": 1,
                "start": 12.5,
                "end": 45.0,
                "rationale": "Why this moment is compelling.",
                "score": 0.92,
                "suggested_clip_title": "Optional short title for this clip.",
            }
        ],
    }

    return (
        f"Video duration: {video_duration:.1f} seconds.\n\n"
        f"Timestamped transcript:\n{transcript_lines}{downsample_note}\n\n"
        f"Detected scene boundaries:\n{scene_lines}\n\n"
        f"Identify up to {num_highlights} highlight-worthy moments, ranked by how "
        f"compelling they are for a short-form video, each between roughly 5 and 60 "
        f"seconds long. Respond with JSON matching exactly this shape:\n"
        f"{json.dumps(schema_example, indent=2)}"
    )


_JSON_OBJECT_RE = re.compile(r"\{.*\}", re.DOTALL)


def parse_analysis_response(raw_text: str) -> AnalysisSchema:
    """Extract and validate a JSON object from a raw LLM completion.

    Tolerates responses wrapped in markdown code fences or preceded/followed
    by stray commentary (common even with "JSON-only" instructions) by
    extracting the first top-level `{...}` block before parsing.

    Raises:
        ProviderResponseParseError: no JSON object found, or it doesn't
            match AnalysisSchema.
    """
    match = _JSON_OBJECT_RE.search(raw_text)
    if not match:
        raise ProviderResponseParseError(f"No JSON object found in response: {raw_text[:200]!r}")

    try:
        payload = json.loads(match.group(0))
    except json.JSONDecodeError as exc:
        raise ProviderResponseParseError(f"Response is not valid JSON: {exc}") from exc

    try:
        return AnalysisSchema.model_validate(payload)
    except ValidationError as exc:
        raise ProviderResponseParseError(f"Response did not match schema: {exc}") from exc


def generate_analysis_with_repair(
    *,
    send_chat: Callable[[ChatMessages], str],
    transcript: TranscriptionResult,
    scenes: list[SceneDTO],
    video_duration: float,
    num_highlights: int = DEFAULT_NUM_HIGHLIGHTS,
) -> tuple[AnalysisSchema, str]:
    """Shared provider-agnostic flow: build the prompt, send it via the
    caller-supplied `send_chat` transport, parse/validate the response, and
    make exactly one repair attempt if parsing fails.

    `send_chat` is a thin closure each provider supplies (e.g. an httpx POST
    to Ollama's or OpenRouter's chat endpoint) so this function stays free
    of any HTTP/provider-specific concerns.

    Returns the validated schema plus the raw text that produced it (the
    caller persists the raw text as an audit trail).
    """
    user_prompt = build_prompt(
        transcript=transcript,
        scenes=scenes,
        video_duration=video_duration,
        num_highlights=num_highlights,
    )
    messages: ChatMessages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": user_prompt},
    ]

    raw = send_chat(messages)
    try:
        return parse_analysis_response(raw), raw
    except ProviderResponseParseError:
        messages.append({"role": "assistant", "content": raw})
        messages.append({"role": "user", "content": REPAIR_PROMPT})
        raw_retry = send_chat(messages)
        # Second failure propagates as ProviderResponseParseError (permanent,
        # no further retries) — the caller's Celery task will not retry it.
        return parse_analysis_response(raw_retry), raw_retry


def schema_to_dto(
    schema: AnalysisSchema, *, provider: str, model: str, raw_text: str
) -> AnalysisDTO:
    return AnalysisDTO(
        summary=schema.summary,
        suggested_title=schema.suggested_title,
        suggested_description=schema.suggested_description,
        suggested_hashtags=schema.suggested_hashtags,
        highlights=[
            HighlightDTO(
                rank=h.rank,
                start=h.start,
                end=h.end,
                rationale=h.rationale,
                score=h.score,
                suggested_clip_title=h.suggested_clip_title,
            )
            for h in schema.highlights
        ],
        provider=provider,
        model=model,
        raw_response={"raw_text": raw_text},
    )
