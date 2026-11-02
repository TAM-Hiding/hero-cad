"""Small appearance-only bridge from Preferences to existing widgets and actors."""
from PySide6.QtCore import QObject, Signal, QSaveFile, QIODevice
from PySide6.QtGui import QColor, QPalette
from hero_cad.palette import COLORS, PREFIX, ENABLED, hex_color, rgb, decode_palette, encode_palette
from hero_cad.ui.feature_icons import feature_icon


def contrast(a, b):
    def luminance(c):
        values = [(v/12.92 if v <= .04045 else ((v+.055)/1.055)**2.4) for v in rgb(c)]
        return sum(a*b for a,b in zip(values, (.2126, .7152, .0722)))
    x, y = sorted((luminance(a), luminance(b)))
    return (y+.05)/(x+.05)


def readable(text, background):
    if contrast(text, background) >= 4.5:
        return text
    return max(('#000000', '#FFFFFF'), key=lambda c:contrast(c, background))


class PaletteController(QObject):
    changed = Signal()

    def __init__(self, window):
        super().__init__(window)
        self.window, self.store = window, window.preference_store
        p = window.palette()
        roles = {'ui.background':QPalette.Window, 'browser.background':QPalette.Base,
                 'properties.background':QPalette.Window, 'ui.text':QPalette.WindowText,
                 'ui.heading':QPalette.WindowText, 'dialogs.background':QPalette.Window, 'controls.normal':QPalette.Button,
                 'controls.text':QPalette.ButtonText, 'controls.selection':QPalette.Highlight,
                 'controls.selection_text':QPalette.HighlightedText, 'controls.input':QPalette.Base,
                 'controls.input_text':QPalette.Text, 'history.selection':QPalette.Highlight}
        self.defaults = {key:spec.default or p.color(roles[key]).name().upper() for key,spec in COLORS.items()}
        self.base_styles = {widget:widget.styleSheet() for widget in (
            window, window.tool_island, window.operation_panel, window.viewport.dimensions)}
        v, s = window.viewport, window.viewport.sketch
        self.actors = {'sketch.normal':s.actor, 'sketch.active':s.foreground_actor,
                       'sketch.selected':s.highlight_actor, 'sketch.profile':v.profiles.actor,
                       'sketch.preview':s.preview_actor, 'sketch.origin':s.origin_actor,
                       'sketch.support':v.support_actor, 'operation.preview':window.operation_panel.actor}
        self.actor_defaults = {key:actor.GetProperty().GetColor() for key,actor in self.actors.items()}
        self.background = v.renderer.GetBackground()
        window.property_info.setProperty('paletteRole', 'secondary')
        from PySide6.QtWidgets import QLabel
        for label in window.tool_island.header.findChildren(QLabel):
            label.setProperty('paletteRole', 'heading')
        window.tool_island.context_hint.setProperty('paletteRole', 'secondary')
        self.store.batch_changed.connect(self.preferences_changed)
        self.apply()

    def overrides(self):
        return {key:self.store.get(PREFIX+key) for key in COLORS if self.store.get(PREFIX+key) is not None} if self.store.get(ENABLED) else {}

    def colors(self):
        overrides = self.overrides()
        colors = {**self.defaults, **overrides}
        if 'ui.background' in overrides and 'dialogs.background' not in overrides:
            colors['dialogs.background'] = overrides['ui.background']
        return colors

    def set_color(self, key, value):
        if key not in COLORS:
            raise ValueError('Unknown palette property')
        self.store.set_many({PREFIX+key:hex_color(value), ENABLED:True})

    def preset(self, custom):
        self.store.set(ENABLED, bool(custom))

    def reset(self, keys=None):
        keys = tuple(COLORS) if keys is None else tuple(keys)
        if any(key not in COLORS for key in keys):
            raise ValueError('Unknown palette property')
        self.store.set_many({PREFIX+key:None for key in keys})

    def export_file(self, path):
        data = encode_palette(self.colors(), self.overrides()).encode('utf-8')
        file = QSaveFile(str(path))
        if not file.open(QIODevice.WriteOnly) or file.write(data) != len(data) or not file.commit():
            raise OSError('Could not save palette: '+file.errorString())

    def import_file(self, path):
        with open(path, 'r', encoding='utf-8') as file:
            colors = decode_palette(file.read(65537))
        self.store.set_many({**{PREFIX+key:value for key,value in colors.items()}, ENABLED:True})

    def preferences_changed(self, keys):
        if any(key.startswith(PREFIX) for key in keys):
            self.apply()
            self.changed.emit()

    def controls(self, scope, colors, fallback):
        o = self.overrides()
        rules = []
        def rule(selectors, values):
            if values:
                rules.append(', '.join((scope+' '+x).strip() for x in selectors.split(','))+' {'+';'.join(values)+';}')
        def pair(selectors, bg, fg, base_bg, base_fg):
            if bg in o or fg in o or 'ui.text' in o:
                background = o.get(bg, base_bg)
                rule(selectors, ['background-color:'+background, 'color:'+readable(o.get(fg, base_fg), background)])
        pair('QPushButton,QToolButton', 'controls.normal', 'controls.text', *fallback['button'])
        pair('QPushButton:checked,QPushButton:pressed,QToolButton:checked,QToolButton:pressed',
             'controls.active', 'controls.active_text', *fallback['active'])
        if 'controls.hover' in o:
            rule('QPushButton:hover,QToolButton:hover', ['background-color:'+o['controls.hover'],
                 'color:'+readable(colors['controls.text'], o['controls.hover'])])
        pair('QPushButton:disabled,QToolButton:disabled', 'controls.disabled', 'controls.disabled_text', *fallback['disabled'])
        pair('QLineEdit,QDoubleSpinBox,QSpinBox,QComboBox,QPlainTextEdit,QComboBox QAbstractItemView',
             'controls.input', 'controls.input_text', *fallback['input'])
        if 'controls.input_border' in o:
            rule('QLineEdit,QDoubleSpinBox,QSpinBox,QComboBox', ['border:1px solid '+o['controls.input_border']])
        if any(key.startswith('controls.') for key in o):
            focus = readable(colors['controls.focus'], o.get('controls.input', fallback['input'][0]))
            rule('QPushButton:focus,QToolButton:focus,QLineEdit:focus,QDoubleSpinBox:focus,QSpinBox:focus,QComboBox:focus',
                 ['border:2px solid '+focus])
        return '\n'.join(rules)

    def apply_widgets(self, o):
        w = self.window
        colors = self.colors()
        rules = []
        def rule(selector, declarations):
            rules.append(selector+' {'+declarations+';}')
        if 'ui.background' in o:
            rule('QMainWindow,QMenuBar,QMenu,QToolBar,QStatusBar,QHeaderView::section,QTabBar::tab', 'background-color:'+o['ui.background']+';color:'+readable(colors['ui.text'],o['ui.background']))
        for key, scope in (('browser.background','QTreeWidget#modelBrowser'),
                           ('properties.background','QTabWidget#propertiesPanel, QTabWidget#propertiesPanel QStackedWidget, QTabWidget#propertiesPanel QStackedWidget > QWidget'),
                           ('dialogs.background','QDialog')):
            if key in o:
                rule(scope, 'background-color:'+o[key]+';color:'+readable(colors['ui.text'], o[key]))
        if 'ui.text' in o:
            rule('QWidget', 'color:'+readable(o['ui.text'], colors['ui.background']))
        if 'ui.secondary' in o:
            rule('QLabel[paletteRole="secondary"]', 'color:'+readable(o['ui.secondary'], colors['ui.background']))
        if 'ui.border' in o:
            rule('QDockWidget,QTabWidget::pane', 'border:1px solid '+o['ui.border'])
        if 'ui.heading' in o:
            rule('QDockWidget::title,QHeaderView::section,QTabBar::tab', 'color:'+readable(o['ui.heading'], colors['ui.background']))
        if 'controls.selection' in o or 'controls.selection_text' in o:
            bg = colors['controls.selection']
            rule('QTreeWidget#modelBrowser', 'selection-background-color:'+bg+';selection-color:'+readable(colors['controls.selection_text'],bg))
        if 'history.selection' in o:
            rule('QPlainTextEdit#historyInspector', 'selection-background-color:'+o['history.selection']+
                 ';selection-color:'+readable(colors['ui.text'],o['history.selection']))
        if any(key in o for key in ('ui.background','dialogs.background','ui.text')):
            dialog_background = o.get('dialogs.background', o.get('ui.background', self.defaults['dialogs.background']))
            dialog_text = readable(colors['ui.text'], dialog_background)
            rule('QDialog,QDialog QWidget', 'background-color:'+dialog_background+';color:'+dialog_text)
            rule('QDialog QTabBar::tab', 'color:'+readable(colors['ui.heading'],dialog_background))
        native = {'button':(colors['controls.normal'],colors['controls.text']),
                  'active':(colors['controls.active'],colors['controls.active_text']),
                  'disabled':(colors['controls.disabled'],colors['controls.disabled_text']),
                  'input':(colors['controls.input'],colors['controls.input_text'])}
        rules.append(self.controls('', colors, native))
        # Properties' explicit child backgrounds need equally scoped control rules.
        rules.append(self.controls('QTabWidget#propertiesPanel', colors, native))
        rules.append(self.controls('QDialog', colors, native))
        self.install_style(w, rules)
        for widget, scope, bg, defaults in (
                (w.tool_island,'QFrame#toolIsland','tools.background',
                 {'button':('#33434B','#DAE5E3'),'active':('#865227','#FFE2B4'),
                  'disabled':('#29353C','#7E9094'),'input':('#33434B','#DAE5E3')}),
                (w.operation_panel,'QWidget#operationSurface','operation.background',
                 {'button':('#4A433D','#F2EAE1'),'active':('#D9B590','#241C16'),
                  'disabled':('#65574C','#C5B6A8'),'input':('#302D2A','#F2EAE1')}),
                (w.viewport.dimensions,'QWidget#constructionDimensions','operation.background',
                 {'button':('#4A433D','#F2EAE1'),'active':('#D9B590','#241C16'),
                  'disabled':('#65574C','#C5B6A8'),'input':('#302D2A','#F2EAE1')})):
            extra = []
            if bg in o:
                extra.append(scope+' {background-color:'+o[bg]+';}')
            if 'ui.border' in o:
                extra.append(scope+' {border-color:'+o['ui.border']+';}')
            if bg in o or 'ui.text' in o or bg == 'operation.background' and 'operation.text' in o:
                text = readable(o.get('operation.text', o.get('ui.text', '#241C16')) if bg == 'operation.background' else colors['ui.text'], colors[bg])
                extra.append(scope+' QLabel {color:'+text+';}')
            if 'ui.secondary' in o:
                extra.append(scope+' QLabel[paletteRole="secondary"] {color:'+readable(o['ui.secondary'],colors[bg])+';}')
            if 'ui.heading' in o:
                extra.append(scope+' QLabel[paletteRole="heading"] {color:'+readable(o['ui.heading'], colors[bg])+';}')
            if widget is w.operation_panel and 'operation.surround' in o:
                extra.append('QDockWidget#operationDialog, QDockWidget#operationDialog::title, QScrollArea#operationScroll, QWidget#operationScrollViewport {background-color:'+o['operation.surround']+';}')
            extra.append(self.controls(scope, colors, defaults))
            self.install_style(widget, extra)
        self.apply_diagnostic()

    def install_style(self, widget, rules):
        extra = '\n'.join(rule for rule in rules if rule)
        style = self.base_styles[widget]+('\n'+extra if extra else '')
        if widget.styleSheet() != style:
            widget.setStyleSheet(style)

    def apply_diagnostic(self):
        # Diagnostic labels retain full text; only their foreground changes.
        w, o, colors = self.window, self.overrides(), self.colors()
        panel = w.operation_panel
        role = panel.feedback.property('paletteDiagnostic')
        if role:
            panel.feedback.setStyleSheet('color:'+readable(o['diagnostics.'+role], colors['operation.background'])+';' if 'diagnostics.'+role in o else '')

    def apply(self):
        w, o = self.window, self.overrides()
        v, s = w.viewport, w.viewport.sketch
        self.apply_widgets(o)
        v.palette_colors = {key:rgb(value) for key,value in o.items()}
        v.renderer.SetBackground(*(rgb(o['viewport.background']) if 'viewport.background' in o else self.background))
        for key, actor in self.actors.items():
            actor.GetProperty().SetColor(*(rgb(o[key]) if key in o else self.actor_defaults[key]))
        if s.snap_result:
            defaults = {'ORIGIN':(1.,.35,.9), 'CENTER':(.35,.65,1.), 'GRID':(1.,.85,.25)}
            s.snap_actor.GetProperty().SetColor(*v.palette_rgb('snap.'+s.snap_result.target.lower(), defaults[s.snap_result.target]))
        v.apply_solid_style()
        s.guides.apply_colors()
        for feature in w.document.features:
            key = ('sketch' if feature.type == 'sketch' else feature.type, feature.id)
            item = w.browser_items.get(key)
            if item is not None:
                status = w.document.statuses[feature.id]
                state = 'valid' if status.valid else 'blocked' if status.blocked_by else 'unresolved'
                item.setIcon(0, feature_icon(feature, state, self))
        v.GetRenderWindow().Render()
