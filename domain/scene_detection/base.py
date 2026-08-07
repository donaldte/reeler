from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path
from typing import ClassVar


@dataclass(frozen=True)
class SceneDTO:
    index: int
    start: float
    end: float


class SceneDetector(ABC):
    """Interface every scene-detection backend must implement."""

    name: ClassVar[str]

    @abstractmethod
    def detect(self, video_path: Path) -> list[SceneDTO]:
        raise NotImplementedError
