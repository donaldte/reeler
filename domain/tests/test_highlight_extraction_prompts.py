import json

import pytest

from domain.ai.prompts.highlight_extraction import (
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


def test_generate_analysis_with_repair_succeeds_first_try():
    calls = []

    def send_chat(messages):
        calls.append(messages)
        return json.dumps(VALID_PAYLOAD)

    schema, _raw = generate_analysis_with_repair(
        send_chat=send_chat, transcript=_transcript(), scenes=_scenes(), video_duration=10.0
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
        send_chat=send_chat, transcript=_transcript(), scenes=_scenes(), video_duration=10.0
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


def test_schema_to_dto_maps_all_fields():
    schema = parse_analysis_response(json.dumps(VALID_PAYLOAD))
    dto = schema_to_dto(schema, provider="ollama", model="qwen2.5:3b", raw_text="{}")
    assert dto.provider == "ollama"
    assert dto.model == "qwen2.5:3b"
    assert dto.highlights[0].rationale == "Great hook."
    assert dto.raw_response == {"raw_text": "{}"}
