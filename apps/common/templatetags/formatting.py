from django import template

register = template.Library()


@register.filter
def seconds_to_timestamp(value: float | int | None) -> str:
    """Render a float number of seconds as `HH:MM:SS.mmm` (or `MM:SS.mmm`
    when under an hour) for transcript/scene/highlight displays.
    """
    if value is None:
        return "--:--"
    total_ms = round(float(value) * 1000)
    hours, rem_ms = divmod(total_ms, 3_600_000)
    minutes, rem_ms = divmod(rem_ms, 60_000)
    seconds, ms = divmod(rem_ms, 1000)
    if hours:
        return f"{hours:02d}:{minutes:02d}:{seconds:02d}.{ms:03d}"
    return f"{minutes:02d}:{seconds:02d}.{ms:03d}"
