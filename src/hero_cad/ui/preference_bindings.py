"""Keep existing QAction/widget callbacks as the sole application behavior paths."""
from PySide6.QtCore import QPoint


def bind_preferences(w):
    store = w.preference_store
    setters = {}

    def bind(key, widget, signal, setter):
        setters[key] = setter
        signal.connect(lambda value, name=key: store.set(name, value))

    for key, action in (
            ('grid/v1/grid_visible', w.grid_action),
            ('grid/v1/scale_visible', w.grid_scale_action),
            ('grid/v1/fade_xray', w.grid_fade_action),
            ('grid/v1/snap_grid', w.snap_grid_action),
            ('grid/v1/snap_origin', w.snap_origin_action),
            ('grid/v1/snap_center', w.snap_center_action),
            ('grid/v1/automatic', w.auto_grid_action),
            ('viewport/v1/axes_visible', w.axes_action),
            ('viewport/v1/auto_hide_sketches', w.auto_hide_sketches),
            ('tool_island/v1/visible', w.island_action)):
        bind(key, action, action.toggled, action.setChecked)
    for key, widget in (('grid/v1/color', w.grid_color), ('viewport/v1/xray', w.xray_choice)):
        bind(key, widget, widget.currentTextChanged, widget.setCurrentText)
    for key, widget in (('grid/v1/manual_spacing', w.manual_grid_spacing),
                        ('viewport/v1/edge_tolerance', w.pick_radius),
                        ('interface/v1/dimension_opacity', w.dimension_opacity)):
        bind(key, widget, widget.valueChanged, widget.setValue)

    def contrast(value):
        w.contrast_actions[value].setChecked(True)
        w.viewport.set_contrast_mode(value)

    def display(value):
        w.display_actions[value].setChecked(True)
        if w.viewport.display_mode != value:
            w.viewport.set_display_mode(value)

    def position(_):
        x, y = store.get('tool_island/v1/x'), store.get('tool_island/v1/y')
        w.tool_island.preferred_position = QPoint(x, y) if x is not None and y is not None else None
        w.tool_island.apply_geometry()

    def sketch_presentation(_):
        v = w.viewport
        v.sketch_xray = store.get('viewport/v1/sketch_xray')
        v.sketch_opacity = store.get('viewport/v1/sketch_opacity') / 100
        v.sketch_face_enabled = store.get('viewport/v1/sketch_face')
        v.apply_solid_style()
        w.update_sketch_face()
        v.GetRenderWindow().Render()

    for key in ('viewport/v1/sketch_xray', 'viewport/v1/sketch_opacity', 'viewport/v1/sketch_face'):
        setters[key] = sketch_presentation
    setters.update({'viewport/v1/contrast': contrast, 'viewport/v1/display_mode': display,
                    'tool_island/v1/size': w.tool_island.set_preset,
                    'tool_island/v1/collapsed': w.tool_island.set_collapsed,
                    'tool_island/v1/x': position, 'tool_island/v1/y': position})
    w.viewport.xrayChanged.connect(lambda value: store.set('viewport/v1/xray', value))
    w.viewport.displayModeChanged.connect(lambda value: store.set('viewport/v1/display_mode', value))
    applying = set()

    def apply(key, value):
        if key not in setters or key in applying:
            return
        applying.add(key)
        try:
            setters[key](value)
        finally:
            applying.remove(key)

    # Freeze the initial snapshot: island setters can publish associated layout values.
    initial = tuple((key, store.get(key)) for key in setters)
    store.changed.connect(apply)
    for key, value in initial:
        apply(key, value)
