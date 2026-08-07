import pytest

from apps.common.templatetags.formatting import seconds_to_timestamp


@pytest.mark.parametrize(
    ("seconds", "expected"),
    [
        (None, "--:--"),
        (0, "00:00.000"),
        (5.5, "00:05.500"),
        (65, "01:05.000"),
        (3661.25, "01:01:01.250"),
    ],
)
def test_seconds_to_timestamp(seconds, expected):
    assert seconds_to_timestamp(seconds) == expected
