"""Small typed catalogue over the application's existing QSettings keys."""
from dataclasses import dataclass
from math import isfinite
from PySide6.QtCore import QObject, Signal


@dataclass(frozen=True)
class Preference:
    category: str
    label: str
    default: object
    kind: type
    choices: tuple = ()
    minimum: float = 0
    maximum: float = 100
    exposed: bool = True

    def validated(self, value, *, stored=False):
        if value is None and self.default is None:
            return None
        if self.kind is bool:
            if type(value) is bool:
                return value
            if stored and isinstance(value, str) and value.lower() in ('true', 'false'):
                return value.lower() == 'true'
        elif self.kind is str:
            if isinstance(value, str) and value in self.choices:
                return value
        elif type(value) is not bool:
            try:
                number = float(value) if stored else value
                if type(number) not in (float, int) or not isfinite(number):
                    raise ValueError()
                if self.minimum <= number <= self.maximum and (self.kind is float or int(number) == number):
                    return self.kind(number)
            except (ValueError, TypeError, OverflowError):
                pass
        raise ValueError('Invalid preference value: '+self.label)


CATEGORIES = ('Appearance', 'Grid & Snapping', 'Viewport', 'Sketching', 'Interface')
PREFERENCES = {
    'viewport/v1/sketch_xray': Preference('Viewport', 'Enable Sketch X-Ray', True, bool),
    'viewport/v1/sketch_opacity': Preference('Viewport', 'Sketch X-Ray Opacity (%)', 35, int),
    'viewport/v1/sketch_face': Preference('Viewport', 'Highlight Active Sketch Face', True, bool),
    'viewport/v1/contrast': Preference('Appearance', 'High-Contrast Geometry', 'Auto', str, ('Off', 'Auto', 'Always')),
    'grid/v1/grid_visible': Preference('Grid & Snapping', 'Show grid', True, bool),
    'grid/v1/color': Preference('Grid & Snapping', 'Grid color', 'Light Grey', str, ('Light Grey', 'White', 'Orange', 'Purple', 'Celadon')),
    'grid/v1/scale_visible': Preference('Grid & Snapping', 'Numeric grid scale labels', False, bool),
    'grid/v1/fade_xray': Preference('Grid & Snapping', 'Fade grid in X-Ray', False, bool),
    'grid/v1/snap_grid': Preference('Grid & Snapping', 'Snap to Grid', True, bool),
    'grid/v1/snap_origin': Preference('Grid & Snapping', 'Origin Snap', True, bool),
    'grid/v1/snap_center': Preference('Grid & Snapping', 'Center Snap', True, bool),
    'grid/v1/automatic': Preference('Grid & Snapping', 'Automatic grid spacing', True, bool),
    'grid/v1/manual_spacing': Preference('Grid & Snapping', 'Manual minor interval (mm)', 1., float, minimum=.000001, maximum=100000),
    'viewport/v1/xray': Preference('Viewport', 'X-Ray mode', 'Off', str, ('Off', 'Celadon', 'Orange')),
    'viewport/v1/edge_tolerance': Preference('Viewport', 'Edge selection hitbox (px)', 6, int, minimum=2, maximum=10),
    'viewport/v1/display_mode': Preference('Viewport', 'Display mode', 'Shaded with CAD Edges', str, ('Shaded with CAD Edges', 'Shaded', 'CAD Wireframe', 'Mesh Debug')),
    'viewport/v1/axes_visible': Preference('Viewport', 'World origin axes', True, bool),
    'viewport/v1/auto_hide_sketches': Preference('Sketching', 'Auto-Hide Consumed Sketches', True, bool),
    'interface/v1/dimension_opacity': Preference('Sketching', 'Dimension popup opacity (%)', 100, int),
    'tool_island/v1/visible': Preference('Interface', 'Show floating tool island', True, bool),
    'tool_island/v1/size': Preference('Interface', 'Tool island size', 'Medium', str, ('Compact', 'Medium', 'Expanded')),
    'tool_island/v1/collapsed': Preference('Interface', 'Collapse tool island', False, bool),
    'tool_island/v1/x': Preference('Interface', 'Island horizontal position', None, int, minimum=-10000000, maximum=10000000, exposed=False),
    'tool_island/v1/y': Preference('Interface', 'Island vertical position', None, int, minimum=-10000000, maximum=10000000, exposed=False),
}


class Preferences(QObject):
    changed = Signal(str, object)

    def __init__(self, settings, parent=None):
        super().__init__(parent)
        self.settings = settings
        self.values = {}
        for key, spec in PREFERENCES.items():
            try:
                self.values[key] = spec.validated(settings.value(key, spec.default), stored=True)
            except ValueError:
                self.values[key] = spec.default

    def get(self, key):
        return self.values[key]

    def set(self, key, value):
        value = PREFERENCES[key].validated(value)
        if self.values[key] == value:
            return
        self.values[key] = value
        if value is None:
            self.settings.remove(key)
        else:
            self.settings.setValue(key, value)
        self.settings.sync()
        self.changed.emit(key, value)

    def restore_category(self, category):
        if category not in CATEGORIES:
            raise ValueError('Unknown preference category')
        for key, spec in PREFERENCES.items():
            if spec.category == category:
                self.set(key, spec.default)
