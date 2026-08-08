from dataclasses import dataclass


@dataclass(frozen=True)
class ClipSpec:
    """A single highlight selected for inclusion in the final render,
    expressed in the *source* video's original timeline.
    """

    start: float
    end: float
    rank: int  # original highlight rank — kept for traceability/debugging only

    @property
    def duration(self) -> float:
        return self.end - self.start


@dataclass(frozen=True)
class CropParams:
    """ffmpeg `crop=W:H:X:Y` parameters, already center-aligned and
    rounded to even numbers — see domain.rendering.dimensions.compute_crop_params.
    """

    width: int
    height: int
    x: int
    y: int


@dataclass(frozen=True)
class OutputDimensions:
    width: int
    height: int
