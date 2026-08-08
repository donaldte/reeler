import json

import pytest

from domain.ai.prompts.highlight_extraction import (
    MAX_TRANSCRIPT_CHARS_IN_PROMPT,
    build_prompt,
    generate_analysis_with_repair,
    parse_analysis_response,
    schema_to_dto,
)
from domain.exceptions import ProviderResponseParseError
from domain.scene_detection.base import SceneDTO
from domain.transcription.base import TranscriptionResult, TranscriptSegmentDTO

VALID_PAYLOAD = {
    "summary": "A video about testing.",
    "suggested_title": "Testing Rocks",
    "suggested_description": "Why tests matter.",
    "suggested_hashtags": ["#testing", "#python"],
    "highlights": [
        {
            "rank": 1,
            "start": 1.0,
            "end": 5.0,
            "rationale": "Great hook.",
            "score": 0.9,
            "suggested_clip_title": "The Hook",
        }
    ],
}


def _transcript() -> TranscriptionResult:
    return TranscriptionResult(
        language="en",
        language_confidence=0.99,
        full_text="Hello world.",
        segments=[TranscriptSegmentDTO(index=0, start=0.0, end=2.0, text="Hello world.")],
        provider="faster_whisper",
        model="small",
    )


def _scenes() -> list[SceneDTO]:
    return [SceneDTO(index=0, start=0.0, end=10.0)]


def test_parse_analysis_response_extracts_json_from_fenced_response():
    raw = f"```json\n{json.dumps(VALID_PAYLOAD)}\n```"
    schema = parse_analysis_response(raw)
    assert schema.summary == "A video about testing."
    assert schema.highlights[0].rank == 1


def test_parse_analysis_response_raises_on_missing_json():
    with pytest.raises(ProviderResponseParseError, match="No JSON object"):
        parse_analysis_response("sorry, I can't help with that")


def test_parse_analysis_response_raises_on_schema_mismatch():
    bad_payload = {**VALID_PAYLOAD, "highlights": "not-a-list"}
    with pytest.raises(ProviderResponseParseError, match="did not match schema"):
        parse_analysis_response(json.dumps(bad_payload))


def _payload_with_highlights(count: int) -> dict:
    """VALID_PAYLOAD's `highlights` array has exactly one entry, which
    would spuriously trigger the count-repair path against
    DEFAULT_NUM_HIGHLIGHTS (3) in tests that don't care about count
    adherence -- this builds a payload with an arbitrary highlight count
    for the tests that do.
    """
    return {
        **VALID_PAYLOAD,
        "highlights": [
            {
                "rank": i + 1,
                "start": float(i * 5),
                "end": float(i * 5 + 4),
                "rationale": f"Highlight {i}.",
                "score": 0.8,
                "suggested_clip_title": f"Clip {i}",
            }
            for i in range(count)
        ],
    }


def test_generate_analysis_with_repair_succeeds_first_try():
    calls = []

    def send_chat(messages):
        calls.append(messages)
        return json.dumps(VALID_PAYLOAD)

    # num_highlights=1 matches VALID_PAYLOAD's single highlight -- this
    # test is about the first-try-succeeds path, not count adherence.
    schema, _raw = generate_analysis_with_repair(
        send_chat=send_chat,
        transcript=_transcript(),
        scenes=_scenes(),
        video_duration=10.0,
        num_highlights=1,
    )
    assert schema.suggested_title == "Testing Rocks"
    assert len(calls) == 1


def test_generate_analysis_with_repair_retries_once_on_bad_json():
    calls = []

    def send_chat(messages):
        calls.append(messages)
        if len(calls) == 1:
            return "not json at all, sorry"
        return json.dumps(VALID_PAYLOAD)

    schema, _raw = generate_analysis_with_repair(
        send_chat=send_chat,
        transcript=_transcript(),
        scenes=_scenes(),
        video_duration=10.0,
        num_highlights=1,
    )
    assert schema.suggested_title == "Testing Rocks"
    assert len(calls) == 2
    # second call includes the repair instruction appended to the conversation
    assert calls[1][-1]["content"].startswith("Your previous response")


def test_generate_analysis_with_repair_raises_after_second_failure():
    def send_chat(messages):
        return "still not json"

    with pytest.raises(ProviderResponseParseError):
        generate_analysis_with_repair(
            send_chat=send_chat, transcript=_transcript(), scenes=_scenes(), video_duration=10.0
        )


def test_generate_analysis_with_repair_retries_once_on_short_count():
    """The count-repair path: a first response that parses fine but comes
    up short on highlights gets exactly one targeted retry, not treated
    as a parse failure and not looped indefinitely.
    """
    calls = []

    def send_chat(messages):
        calls.append(messages)
        if len(calls) == 1:
            return json.dumps(_payload_with_highlights(1))
        return json.dumps(_payload_with_highlights(3))

    schema, _raw = generate_analysis_with_repair(
        send_chat=send_chat,
        transcript=_transcript(),
        scenes=_scenes(),
        video_duration=10.0,
        num_highlights=3,
    )
    assert len(schema.highlights) == 3
    assert len(calls) == 2
    # the repair message is count-specific, not the generic JSON-repair one
    assert "only included 1 highlight" in calls[1][-1]["content"]


def test_generate_analysis_with_repair_keeps_original_when_repair_also_short():
    calls = []

    def send_chat(messages):
        calls.append(messages)
        return json.dumps(_payload_with_highlights(1))

    schema, _raw = generate_analysis_with_repair(
        send_chat=send_chat,
        transcript=_transcript(),
        scenes=_scenes(),
        video_duration=10.0,
        num_highlights=3,
    )
    assert len(schema.highlights) == 1  # short-but-valid is kept, not discarded
    assert len(calls) == 2  # still just one repair attempt, no infinite loop


def test_generate_analysis_with_repair_keeps_original_when_repair_worse():
    calls = []

    def send_chat(messages):
        calls.append(messages)
        if len(calls) == 1:
            return json.dumps(_payload_with_highlights(2))
        return json.dumps(_payload_with_highlights(1))

    schema, _raw = generate_analysis_with_repair(
        send_chat=send_chat,
        transcript=_transcript(),
        scenes=_scenes(),
        video_duration=10.0,
        num_highlights=3,
    )
    assert len(schema.highlights) == 2  # the repair made it worse, original kept


def test_generate_analysis_with_repair_keeps_original_when_repair_fails_to_parse():
    calls = []

    def send_chat(messages):
        calls.append(messages)
        if len(calls) == 1:
            return json.dumps(_payload_with_highlights(1))
        return "not json at all"

    schema, _raw = generate_analysis_with_repair(
        send_chat=send_chat,
        transcript=_transcript(),
        scenes=_scenes(),
        video_duration=10.0,
        num_highlights=3,
    )
    assert len(schema.highlights) == 1  # the original valid-but-short result survives


def test_schema_to_dto_maps_all_fields():
    schema = parse_analysis_response(json.dumps(VALID_PAYLOAD))
    dto = schema_to_dto(schema, provider="ollama", model="qwen2.5:3b", raw_text="{}")
    assert dto.provider == "ollama"
    assert dto.model == "qwen2.5:3b"
    assert dto.highlights[0].rationale == "Great hook."
    assert dto.raw_response == {"raw_text": "{}"}


def _long_transcript(num_segments: int) -> TranscriptionResult:
    """Simulates a long source video: many short segments, each with its
    own timestamp prefix — exactly the shape that blew up the prompt size
    in production (see docs/ai_pipeline.md#operational-notes).
    """
    segments = [
        TranscriptSegmentDTO(
            index=i, start=float(i * 3), end=float(i * 3 + 2.5), text=f"This is segment number {i}."
        )
        for i in range(num_segments)
    ]
    return TranscriptionResult(
        language="en",
        language_confidence=0.9,
        full_text=" ".join(s.text for s in segments),
        segments=segments,
        provider="faster_whisper",
        model="small",
    )


def test_build_prompt_demands_exact_highlight_count_with_two_example_highlights():
    """Regression test for the observed production bug: a model asked for
    3 highlights returned only 1. The schema example now shows two
    highlight objects (not one) and the instruction text is unhedged.
    """
    prompt = build_prompt(
        transcript=_transcript(), scenes=_scenes(), video_duration=10.0, num_highlights=3
    )
    assert "EXACTLY 3" in prompt
    # "up to" is legitimately used elsewhere now (the B-roll suggestion
    # count is intentionally soft) -- only the highlight-count wording
    # itself must stay unhedged.
    assert "up to 3 highlight" not in prompt.lower()
    example_section = prompt.split('"highlights": [', 1)[1]
    assert example_section.count('"rank"') == 2
    assert '"emoji"' in prompt
    assert '"transition"' in prompt


def test_build_prompt_full_video_mode_asks_for_zero_highlights():
    """export_mode="full_video" means the whole source video is kept, not
    cut -- asking for num_highlights moments *to extract* would be
    contextually wrong and would waste CPU-bound generation time.
    """
    prompt = build_prompt(
        transcript=_transcript(),
        scenes=_scenes(),
        video_duration=10.0,
        num_highlights=3,
        export_mode="full_video",
    )
    assert "EXACTLY 3" not in prompt
    assert "highlight-worthy moments" not in prompt
    assert '"highlights": []' in prompt
    example_section = prompt.split('"highlights": [', 1)[1]
    assert example_section.split("]", 1)[0].strip() == ""  # no example highlight objects


def test_build_prompt_full_video_mode_still_asks_for_broll():
    prompt = build_prompt(
        transcript=_transcript(),
        scenes=_scenes(),
        video_duration=10.0,
        num_highlights=3,
        export_mode="full_video",
    )
    assert "broll_suggestions" in prompt
    assert "B-roll moments" in prompt


def test_generate_analysis_with_repair_full_video_mode_never_triggers_count_repair():
    """The model returning zero highlights (as instructed) must not
    spuriously trigger the count-repair path -- target is 0, not
    num_highlights, when export_mode="full_video".
    """
    calls = []

    def send_chat(messages):
        calls.append(messages)
        return json.dumps(_payload_with_highlights(0))

    schema, _raw = generate_analysis_with_repair(
        send_chat=send_chat,
        transcript=_transcript(),
        scenes=_scenes(),
        video_duration=10.0,
        num_highlights=3,
        export_mode="full_video",
    )
    assert schema.highlights == []
    assert len(calls) == 1


def test_generate_analysis_with_repair_full_video_mode_accepts_stray_highlights():
    """If a model ignores the "return highlights: []" instruction and
    returns some anyway, that's harmless (the full-video renderer never
    reads Highlight rows) -- not something to repair away.
    """
    calls = []

    def send_chat(messages):
        calls.append(messages)
        return json.dumps(_payload_with_highlights(2))

    schema, _raw = generate_analysis_with_repair(
        send_chat=send_chat,
        transcript=_transcript(),
        scenes=_scenes(),
        video_duration=10.0,
        num_highlights=3,
        export_mode="full_video",
    )
    assert len(schema.highlights) == 2
    assert len(calls) == 1


def test_highlight_schema_accepts_emoji_and_transition():
    payload = _payload_with_highlights(1)
    payload["highlights"][0]["emoji"] = "🔥"
    payload["highlights"][0]["transition"] = "cut"
    schema = parse_analysis_response(json.dumps(payload))
    assert schema.highlights[0].emoji == "🔥"
    assert schema.highlights[0].transition == "cut"


def test_highlight_schema_rejects_invalid_transition_value():
    payload = _payload_with_highlights(1)
    payload["highlights"][0]["transition"] = "sparkle-wipe"
    with pytest.raises(ProviderResponseParseError, match="did not match schema"):
        parse_analysis_response(json.dumps(payload))


def test_schema_to_dto_maps_emoji_and_transition():
    payload = _payload_with_highlights(1)
    payload["highlights"][0]["emoji"] = "💡"
    payload["highlights"][0]["transition"] = "fade"
    schema = parse_analysis_response(json.dumps(payload))
    dto = schema_to_dto(schema, provider="ollama", model="qwen2.5:3b", raw_text="{}")
    assert dto.highlights[0].emoji == "💡"
    assert dto.highlights[0].transition == "fade"


def test_build_prompt_includes_full_transcript_when_under_budget():
    prompt = build_prompt(transcript=_transcript(), scenes=_scenes(), video_duration=10.0)
    assert "Hello world." in prompt
    assert "downsampled" not in prompt


def test_build_prompt_downsamples_long_transcript_and_stays_bounded():
    # Each segment line is ~35 chars; enough segments to blow past the budget.
    long_transcript = _long_transcript(num_segments=1000)
    raw_full_length = sum(
        len(f"[{s.start:.1f}-{s.end:.1f}] {s.text}\n") for s in long_transcript.segments
    )
    assert raw_full_length > MAX_TRANSCRIPT_CHARS_IN_PROMPT  # sanity check on the fixture

    prompt = build_prompt(transcript=long_transcript, scenes=_scenes(), video_duration=3000.0)

    assert "downsampled for length" in prompt
    # The transcript portion specifically must stay near the budget, not
    # the whole prompt (which also has instructions/schema overhead).
    transcript_section = prompt.split("Timestamped transcript:\n")[1].split(
        "\n\nDetected scene boundaries"
    )[0]
    assert len(transcript_section) < MAX_TRANSCRIPT_CHARS_IN_PROMPT * 1.5


def test_build_prompt_downsampling_preserves_start_and_end_coverage():
    long_transcript = _long_transcript(num_segments=1000)
    prompt = build_prompt(transcript=long_transcript, scenes=_scenes(), video_duration=3000.0)

    assert "segment number 0." in prompt  # first segment kept
    assert "segment number 999." in prompt  # last segment kept too, not just the head
