"""Experimental RGB property catalogue and portable palette JSON, independent of CAD."""
from dataclasses import dataclass
import json
import re

PREFIX = 'palette/v1/'
ENABLED = PREFIX+'enabled'


@dataclass(frozen=True)
class Color:
    category: str
    label: str
    default: str | None  # None: use the platform's existing Qt palette.


COLORS = {}
def category(name, rows):
    for key, label, default in rows:
        COLORS[key] = Color(name, label, default)


category('Windows', (
    ('ui.background', 'Main application background', None),
    ('browser.background', 'Model browser background', None),
    ('properties.background', 'Properties background', None),
    ('tools.background', 'HERO Tools background', '#242E34'),
    ('dialogs.background', 'Dialog backgrounds', None),
    ('operation.background', 'Operation / numeric popup surface', '#B87743'),
    ('operation.surround', 'Operation window surround', '#874923'),
    ('operation.text', 'Operation label text', '#241C16'),
    ('ui.border', 'Panel borders', '#566D72'),
    ('ui.heading', 'Panel headings', None),
    ('ui.text', 'Normal interface text', None),
    ('ui.secondary', 'Secondary interface text', '#BED3D0'),
))
category('Controls', (
    ('controls.normal', 'Normal buttons', None),
    ('controls.active', 'Active buttons', '#865227'),
    ('controls.hover', 'Hovered buttons', '#425960'),
    ('controls.disabled', 'Disabled buttons', '#29353C'),
    ('controls.text', 'Button text', None),
    ('controls.active_text', 'Active button text', '#FFE2B4'),
    ('controls.disabled_text', 'Disabled button text', '#7E9094'),
    ('controls.selection', 'Selected browser entries', None),
    ('controls.selection_text', 'Selected browser text', None),
    ('controls.input', 'Input backgrounds', None),
    ('controls.input_text', 'Input text', None),
    ('controls.input_border', 'Input borders', '#53666D'),
    ('controls.focus', 'Keyboard focus ring', '#D9B590'),
))
category('Sketch', (
    ('sketch.normal', 'Normal sketch entities', '#52B8E0'),
    ('sketch.active', 'Active sketch entities', '#66D9F2'),
    ('sketch.selected', 'Selected sketch entities', '#FFA626'),
    ('sketch.profile', 'Selected material profile fill', '#FFA626'),
    ('sketch.preview', 'Construction preview guides', '#A6F2B2'),
    ('sketch.origin', 'Sketch origin marker', '#CCD9E6'),
    ('snap.grid', 'Grid snap marker', '#FFD940'),
    ('snap.origin', 'Origin snap marker', '#FF59E6'),
    ('snap.center', 'Center snap marker', '#59A6FF'),
    ('grid.major', 'Major grid lines', '#B8C2CC'),
    ('grid.minor', 'Minor grid lines', '#777E85'),
    ('grid.labels', 'Grid labels', '#B8C2CC'),
    ('sketch.support', 'Active support face', '#E6A04B'),
))
category('Viewport', (
    ('viewport.background', 'Viewport background', '#171F29'),
    ('viewport.model', 'Normal model shading', '#A6C9DB'),
    ('viewport.edges', 'Model edge lines', '#213340'),
    ('viewport.contrast_edges', 'High-contrast model edges', '#0E1318'),
    ('viewport.faces', 'Selected faces', '#FFA626'),
    ('viewport.selected_edges', 'Selected edges', '#FFA626'),
    ('xray.orange', 'Orange X-Ray shading', '#FFA626'),
    ('xray.celadon', 'Celadon X-Ray shading', '#A6C9DB'),
    ('xray.orange_highlight', 'Orange X-Ray selection', '#FFEDA6'),
    ('xray.celadon_highlight', 'Celadon X-Ray selection', '#FFA626'),
    ('operation.preview', 'Operation preview shading', '#FFA626'),
))
category('History & Diagnostics', (
    ('history.valid', 'Valid feature indicator', '#65B879'),
    ('history.unresolved', 'Unresolved feature indicator', '#E6A04B'),
    ('history.blocked', 'Blocked feature indicator', '#D95C5C'),
    ('diagnostics.error', 'Error messages', '#D95C5C'),
    ('diagnostics.warning', 'Warning messages', '#E6A04B'),
    ('history.selection', 'Selected history text', None),
))
CATEGORIES = tuple(dict.fromkeys(c.category for c in COLORS.values()))


def hex_color(value):
    if not isinstance(value, str) or not re.fullmatch(r'#[0-9a-fA-F]{6}', value):
        raise ValueError('Colors must be hexadecimal RGB: #RRGGBB')
    return value.upper()


def rgb(value):
    value = hex_color(value)
    return tuple(int(value[i:i+2], 16)/255 for i in (1, 3, 5))


def decode_palette(text):
    """Strict complete v1 snapshots; validate everything before publishing anything."""
    def unique(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError('Duplicate JSON property: '+key)
            result[key] = value
        return result
    if len(text) > 65536:
        raise ValueError('Palette file exceeds 64 KiB')
    data = json.loads(text, object_pairs_hook=unique)
    if (not isinstance(data, dict) or set(data) not in ({'format', 'version', 'colors'}, {'format', 'version', 'colors', 'overrides'})
            or data['format'] != 'hero-ui-palette' or type(data['version']) is not int or data['version'] != 1):
        raise ValueError('Expected hero-ui-palette version 1 with format, version and colors')
    if not isinstance(data['colors'], dict) or set(data['colors']) != set(COLORS):
        raise ValueError('Palette must contain every known color and no unknown properties')
    colors = {key:hex_color(value) for key, value in data['colors'].items()}
    overrides = data.get('overrides', list(COLORS))
    if (not isinstance(overrides, list) or any(not isinstance(key, str) or key not in COLORS for key in overrides)
            or len(set(overrides)) != len(overrides)):
        raise ValueError('Overrides must be unique known color property names')
    return {key:value if key in overrides else None for key,value in colors.items()}


def encode_palette(colors, overrides=None):
    data = {'format':'hero-ui-palette', 'version':1, 'colors':dict(sorted(colors.items()))}
    if overrides is not None:
        data['overrides'] = sorted(overrides)
    text = json.dumps(data, indent=2)+'\n'
    decode_palette(text)
    return text
