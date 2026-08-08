import pytest

from domain.rendering.dimensions import (
    OUTPUT_DIMENSIONS,
    compute_crop_params,
    get_output_dimensions,
)


@pytest.mark.parametrize(("aspect_ratio", "quality"), list(OUTPUT_DIMENSIONS.keys()))
def test_all_output_dimensions_are_even(aspect_ratio, quality):
    dims = get_output_dimensions(aspect_ratio, quality)
    assert dims.width % 2 == 0
    assert dims.height % 2 == 0


def test_get_output_dimensions_raises_on_unknown_combination():
    with pytest.raises(ValueError, match="Unsupported"):
        get_output_dimensions("21:9", "1080p")


def test_crop_wider_source_crops_width():
    # 1920x1080 (16:9) source cropped to 9:16 target -> crop width, keep height
    params = compute_crop_params(1920, 1080, 1080, 1920)
    assert params.height == 1080
    assert params.width < 1920
    assert params.width % 2 == 0
    # centered
    assert params.x == (1920 - params.width) // 2
    assert params.y == 0


def test_crop_taller_source_crops_height():
    # 1080x1920 (9:16) source cropped to 16:9 target -> crop height, keep width
    params = compute_crop_params(1080, 1920, 1920, 1080)
    assert params.width == 1080
    assert params.height < 1920
    assert params.height % 2 == 0
    assert params.y == (1920 - params.height) // 2
    assert params.x == 0


def test_crop_matching_ratio_keeps_full_frame():
    params = compute_crop_params(1920, 1080, 1920, 1080)
    assert params.width == 1920
    assert params.height == 1080
    assert params.x == 0
    assert params.y == 0


def test_crop_square_target_from_landscape():
    params = compute_crop_params(1920, 1080, 1080, 1080)
    assert params.height == 1080
    assert params.width == 1080
    assert params.x == (1920 - 1080) // 2


def test_raises_on_invalid_source_dimensions():
    with pytest.raises(ValueError, match="Invalid source dimensions"):
        compute_crop_params(0, 1080, 1920, 1080)
    with pytest.raises(ValueError, match="Invalid source dimensions"):
        compute_crop_params(1920, -1, 1920, 1080)
