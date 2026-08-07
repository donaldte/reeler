from unittest.mock import MagicMock, patch

import pytest

from apps.transcripts.models import Transcript
from apps.transcripts.tasks import transcribe_video_task
from apps.videos.constants import PIPELINE_STEP_TRANSCRIPT, STEP_DONE, STEP_FAILED
from apps.videos.models import UploadedVideo
from apps.videos.tests.factories import UploadedVideoFactory
from domain.exceptions import PermanentPipelineError
from domain.transcription.base import TranscriptionResult, TranscriptSegmentDTO

pytestmark = pytest.mark.django_db

FAKE_RESULT = TranscriptionResult(
    language="en",
    language_confidence=0.95,
    full_text="Hello world.",
    segments=[TranscriptSegmentDTO(index=0, start=0.0, end=1.5, text="Hello world.")],
    provider="faster_whisper",
    model="small",
)


def test_transcribe_video_task_persists_transcript_and_segments():
    video = UploadedVideoFactory()
    fake_provider = MagicMock()
    fake_provider.transcribe.return_value = FAKE_RESULT

    with patch("apps.transcripts.tasks.get_stt_provider", return_value=fake_provider):
        transcribe_video_task(str(video.id))

    transcript = Transcript.objects.get(video=video)
    assert transcript.language == "en"
    assert transcript.segments.count() == 1
    video.refresh_from_db()
    assert video.pipeline_steps[PIPELINE_STEP_TRANSCRIPT] == STEP_DONE


def test_transcribe_video_task_is_idempotent_on_rerun():
    video = UploadedVideoFactory()
    fake_provider = MagicMock()
    fake_provider.transcribe.return_value = FAKE_RESULT

    with patch("apps.transcripts.tasks.get_stt_provider", return_value=fake_provider):
        transcribe_video_task(str(video.id))
        transcribe_video_task(str(video.id))

    assert Transcript.objects.filter(video=video).count() == 1
    assert Transcript.objects.get(video=video).segments.count() == 1


def test_transcribe_video_task_fails_pipeline_on_permanent_error():
    video = UploadedVideoFactory()
    fake_provider = MagicMock()
    fake_provider.transcribe.side_effect = PermanentPipelineError("bad audio")

    with (
        patch("apps.transcripts.tasks.get_stt_provider", return_value=fake_provider),
        pytest.raises(PermanentPipelineError),
    ):
        transcribe_video_task(str(video.id))

    video.refresh_from_db()
    assert video.status == UploadedVideo.Status.FAILED
    assert video.pipeline_steps[PIPELINE_STEP_TRANSCRIPT] == STEP_FAILED
