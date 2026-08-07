"""Scene-boundary detection via PySceneDetect's ContentDetector.

Returns an empty list when the video has no detectable cuts (e.g. a single
continuous static shot) — callers (apps/scenes/tasks.py) are responsible for
falling back to a single scene spanning the whole video in that case, since
this wrapper intentionally has no knowledge of the video's total duration
beyond what PySceneDetect itself reports.
"""

from pathlib import Path
from typing import ClassVar

from domain.scene_detection.base import SceneDetector, SceneDTO


class PySceneDetectProvider(SceneDetector):
    name: ClassVar[str] = "pyscenedetect"

    def __init__(
        self,
        threshold: float = 27.0,
        min_scene_len_seconds: float = 0.6,
        assumed_fps_for_min_len: float = 30.0,
    ) -> None:
        self.threshold = threshold
        # PySceneDetect's min_scene_len is expressed in frames; we only know
        # the true fps once ffprobe has already run, so this uses a coarse
        # assumed fps for the *minimum scene length* floor only (it does not
        # affect the timestamps returned, which come from PySceneDetect's
        # own frame-accurate FrameTimecode objects).
        self.min_scene_len_frames = max(1, round(min_scene_len_seconds * assumed_fps_for_min_len))

    def detect(self, video_path: Path) -> list[SceneDTO]:
        from scenedetect import ContentDetector, detect  # imported lazily: pulls in OpenCV

        scene_list = detect(
            str(video_path),
            ContentDetector(threshold=self.threshold, min_scene_len=self.min_scene_len_frames),
        )
        return [
            SceneDTO(index=i, start=start.get_seconds(), end=end.get_seconds())
            for i, (start, end) in enumerate(scene_list)
        ]
