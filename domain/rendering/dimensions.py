"""Output-resolution lookup and center-crop math.

Keys are plain strings matching `ExportSettings.AspectRatio`/`VideoQuality`
choice *values* (e.g. "9:16", "1080p") — this module deliberately doesn't
import the Django model (domain/ stays framework-free); callers pass the
values straight out of `RenderJob.settings_snapshot`.
"""

from domain.rendering.dto import CropParams, OutputDimensions

# All dimensions even (required by most video codecs).
OUTPUT_DIMENSIONS: dict[tuple[str, str], OutputDimensions] = {
    ("16:9", "720p"): OutputDimensions(1280, 720),
    ("16:9", "1080p"): OutputDimensions(1920, 1080),
    ("16:9", "4k"): OutputDimensions(3840, 2160),
    ("9:16", "720p"): OutputDimensions(720, 1280),
    ("9:16", "1080p"): OutputDimensions(1080, 1920),
    ("9:16", "4k"): OutputDimensions(2160, 3840),
    ("1:1", "720p"): OutputDimensions(720, 720),
    ("1:1", "1080p"): OutputDimensions(1080, 1080),
    ("1:1", "4k"): OutputDimensions(2160, 2160),
}


def get_output_dimensions(aspect_ratio: str, video_quality: str) -> OutputDimensions:
    try:
        return OUTPUT_DIMENSIONS[(aspect_ratio, video_quality)]
    except KeyError as exc:
        combo = (aspect_ratio, video_quality)
        raise ValueError(f"Unsupported aspect_ratio/video_quality: {combo!r}") from exc


def compute_crop_params(
    src_width: int, src_height: int, target_width: int, target_height: int
) -> CropParams:
    """Center-crop-to-aspect-ratio: crops the source down to the target
    aspect ratio (not the target *resolution* — scaling to the final
    output size happens separately in the ffmpeg `scale` filter) by
    trimming whichever dimension makes the source "too wide" or "too
    tall" relative to the target ratio, centered.
    """
    if src_width <= 0 or src_height <= 0:
        raise ValueError(f"Invalid source dimensions: {src_width}x{src_height}")

    target_ratio = target_width / target_height
    src_ratio = src_width / src_height

    if src_ratio > target_ratio:
        # Source is relatively wider than the target -> crop width.
        crop_height = src_height
        crop_width = round(src_height * target_ratio)
    else:
        # Source is relatively taller/narrower than the target -> crop height.
        crop_width = src_width
        crop_height = round(src_width / target_ratio)

    crop_width -= crop_width % 2
    crop_height -= crop_height % 2
    crop_width = max(crop_width, 2)
    crop_height = max(crop_height, 2)

    crop_x = (src_width - crop_width) // 2
    crop_y = (src_height - crop_height) // 2

    return CropParams(width=crop_width, height=crop_height, x=crop_x, y=crop_y)
