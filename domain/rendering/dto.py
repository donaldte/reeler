from dataclasses import dataclass


@dataclass(frozen=True)
class ClipSpec:
    """A single highlight selected for inclusion in the final render,
    expressed in the *source* video's original timeline.
    """

    start: float
    end: float
    rank: int  # original highlight rank — kept for traceability/debugging only
    emoji: str | None = None
    transition: str | None = None

    @property
    def duration(self) -> float:
        return self.end - self.start


@dataclass(frozen=True)
class BrollSpec:
    """One B-roll still-image overlay window, expressed on the *output*
    (post-concat) timeline -- not the source video's, and not any single
    clip's local timeline (parallels how captions.py remaps segments onto
    the concatenated timeline via cumulative_offset -- see
    domain.rendering.broll.remap_broll_to_output_timeline).

    `image_input_index` is the ffmpeg -i index of this image, assigned by
    the caller (renderer.py) when it appends `-loop 1 -framerate
    BROLL_FPS -i <path>` for each image -- this module only ever reasons
    about indices/timings, never file paths (same separation of concerns
    as ClipSpec/CropParams elsewhere in this file).
    """

    image_input_index: int
    start: float
    end: float
    zoom_direction: str = "in"  # "in" or "out" -- see ZOOM_DIRECTION_PARAMS in broll.py

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
