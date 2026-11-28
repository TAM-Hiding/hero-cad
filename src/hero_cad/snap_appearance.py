"""Appearance-only snap options shared by Preferences and palette files."""
from math import isfinite

PREFIX = 'snap/v1/'
# label, default, type, choices, minimum, maximum
OPTIONS = {
    'midpoint': ('Midpoint symbol', 'Triangle', str, ('Triangle', 'Centerline (C/L)'), 0, 0),
    'color': ('Snap indicator color', 'Palette', str, ('Palette', 'Red', 'Green', 'Blue'), 0, 0),
    'size': ('Snap indicator size (px)', 14, int, (), 8, 40),
    'weight': ('Snap indicator line weight (px)', 1.5, float, (), .5, 4),
    'highlight': ('Highlight acquired model edge', True, bool, (), 0, 0),
    'centerline': ('Show temporary centerline guides', False, bool, (), 0, 0),
    'guide_color': ('Centerline guide color', 'Palette', str, ('Palette', 'Red', 'Green', 'Blue'), 0, 0),
    'guide_style': ('Centerline guide style', 'Dash-dot', str, ('Dashed', 'Dash-dot', 'Dotted'), 0, 0),
}
DEFAULTS = {key: row[1] for key, row in OPTIONS.items()}


def validated_options(values):
    """Validate a partial portable snapshot before any preference is changed."""
    if not isinstance(values, dict) or not set(values).issubset(OPTIONS):
        raise ValueError('Unknown snap indicator settings')
    for key, value in values.items():
        _, _, kind, choices, minimum, maximum = OPTIONS[key]
        if kind is bool:
            valid = type(value) is bool
        elif kind is str:
            valid = type(value) is str and value in choices
        else:
            valid = (type(value) in (int, float) and minimum <= value <= maximum
                     and isfinite(value) and (kind is float or int(value) == value))
        if not valid:
            raise ValueError('Invalid snap indicator setting: '+key)
    return dict(values)
