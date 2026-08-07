# Test fixtures

`sample_5s.mp4` (not included in this scaffold) is meant to be a real,
tiny (~5 second, <1MB) video with both a video and audio stream, used for
**manual, non-mocked** smoke testing against a real ffmpeg/Whisper/Ollama
stack — e.g. via `make shell` + a one-off script, or a future opt-in
"real pipeline" test marked `@pytest.mark.slow`.

The automated test suite (`apps/*/tests/`, `domain/tests/`) deliberately
does **not** depend on this file: every test that would otherwise need
ffprobe, faster-whisper, PySceneDetect, or a live Ollama server mocks that
boundary instead (see `apps/videos/tests/test_pipeline_integration.py`),
so CI stays fast and fully hermetic — no model downloads, no GPU/CPU
transcription cost, no network calls.

To add the real fixture locally:

```bash
ffmpeg -f lavfi -i testsrc=duration=5:size=1280x720:rate=30 \
       -f lavfi -i sine=frequency=440:duration=5 \
       -c:v libx264 -c:a aac -shortest tests/fixtures/sample_5s.mp4
```
