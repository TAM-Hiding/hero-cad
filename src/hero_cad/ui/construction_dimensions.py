"""Small reusable cursor readout/editor; values belong to construction tools only."""
from PySide6.QtCore import Qt, QEvent, QPoint
from PySide6.QtWidgets import QWidget, QVBoxLayout, QLabel, QLineEdit, QGraphicsOpacityEffect


class ConstructionDimensions(QWidget):
    def __init__(self, viewport):
        super().__init__(viewport)
        self.viewport = viewport
        self.names = []
        self.index = 0
        self.editing = False
        self.stage_key = None
        self.anchor_pending = True
        self.opacity = 100
        self.opacity_effect = QGraphicsOpacityEffect(self)
        self.opacity_effect.setOpacity(1.0)
        self.setGraphicsEffect(self.opacity_effect)
        self.label = QLabel()
        self.input = QLineEdit()
        self.input.setPlaceholderText('Type mm · Tab next · Enter place')
        self.input.installEventFilter(self)
        self.input.textEdited.connect(self.preview_text)
        self.input.hide()
        layout = QVBoxLayout(self)
        layout.setContentsMargins(6, 4, 6, 4)
        layout.addWidget(self.label)
        layout.addWidget(self.input)
        self.setAttribute(Qt.WA_StyledBackground, True)
        self.setStyleSheet('ConstructionDimensions {background: #24303c; border: 1px solid #63778b;}'
                          'QLabel {color: #e0ebf5;}'
                          'QLineEdit {color: #e0ebf5; background: #15212c; border: 1px solid #8aacc9; padding: 3px;}')
        self.hide()
        self.cursor_position = QPoint(20, 20)

    def reset(self):
        self.editing = False
        self.stage_key = None
        self.anchor_pending = True
        self.names, self.index = [], 0
        self.input.clear()
        self.input.hide()
        self.hide()

    def update_values(self, position=None):
        tool = self.viewport.sketch.controller.tool
        values = tool.dimension_values() if tool else {}
        if 'Radius' in values:
            radius = tool.dimensions.get('Radius', values['Radius'])
            values = {'Radius': radius, 'Diameter': 2*radius}
        names = list(values)
        stage_key = (id(tool), tool.stage) if tool else None
        stage_changed = stage_key != self.stage_key
        self.stage_key = stage_key
        if stage_changed:
            self.anchor_pending = True
        if names != self.names:
            self.names, self.index = names, 0
            self.input.clear()
        if not values:
            self.reset()
            return
        self.label.setText(' | '.join(f'{n}: {tool.dimensions.get(n, v):.12g} mm' + (' 🔒' if self.parameter_name(n) in tool.dimensions else '')
                                      for n, v in values.items()) + '\nType or Tab to edit · Enter place · Esc cancel')
        self.input.show()
        if not self.editing:
            self.input.setPlaceholderText(self.names[self.index] + ' (mm) — click or type to enter')
        # Keep the editor reachable instead of chasing the cursor. Re-anchor
        # for each construction stage, then freeze while the user types.
        if position is not None and self.anchor_pending and not self.editing:
            self.cursor_position = position.toPoint() if hasattr(position, 'toPoint') else position
            self.anchor_pending = False
        self.adjustSize()
        self.move(max(0, min(self.cursor_position.x()+98, self.viewport.width()-self.width())),
                  max(0, min(self.cursor_position.y()+68, self.viewport.height()-self.height())))
        self.setVisible(self.opacity > 0)
        self.raise_()

    def set_opacity(self, percent):
        self.opacity = max(0, min(100, int(percent)))
        self.opacity_effect.setOpacity(self.opacity / 100)
        if self.opacity == 0:
            self.editing = False
            if self.input.hasFocus():
                self.viewport.setFocus()
            self.hide()
        else:
            self.update_values()

    def begin(self, text=''):
        if not self.names or self.opacity == 0:
            return False
        self.editing = True
        self.input.show()
        self.input.setPlaceholderText(self.names[self.index] + ' (mm)')
        self.input.setText(text)
        self.input.setFocus()
        self.input.setCursorPosition(len(text))
        self.adjustSize()
        self.preview_text(text)
        return True

    def preview_text(self, text):
        """Only valid transient dimensions affect the preview, never the document."""
        tool = self.viewport.sketch.controller.tool
        if not self.editing or not tool or not self.names:
            return
        try:
            self.set_value(tool, float(text))
        except (ValueError, OverflowError):
            return
        self.viewport.sketch.numeric_preview()

    @staticmethod
    def parameter_name(name):
        return 'Radius' if name == 'Diameter' else name

    def set_value(self, tool, value):
        name = self.names[self.index]
        tool.set_dimension(self.parameter_name(name), value/2 if name == 'Diameter' else value)

    def accept_value(self):
        try:
            tool = self.viewport.sketch.controller.tool
            if not tool:
                return False
            if self.input.text().strip():
                self.set_value(tool, float(self.input.text()))
            elif self.parameter_name(self.names[self.index]) not in tool.dimensions:
                raise ValueError('Enter a positive dimension in mm')
        except (ValueError, OverflowError) as error:
            self.viewport.viewFeedback.emit(str(error))
            self.input.selectAll()
            return False
        self.input.clear()
        self.viewport.sketch.numeric_preview()
        return True

    def eventFilter(self, watched, event):
        if event.type() == QEvent.FocusIn and not self.editing and self.names:
            self.begin(self.input.text())
        if event.type() == QEvent.KeyPress:
            if event.key() == Qt.Key_Escape:
                self.viewport.sketch.set_tool('select')
                self.viewport.setFocus()
                return True
            if event.key() in (Qt.Key_Tab, Qt.Key_Backtab):
                # Empty fields can be skipped, including Radius -> Diameter
                # before a number is entered. Invalid text still blocks a switch.
                if not self.input.text().strip() or self.accept_value():
                    self.index = (self.index + ( -1 if event.key() == Qt.Key_Backtab else 1)) % len(self.names)
                    self.input.setPlaceholderText(self.names[self.index] + ' (mm)')
                    tool = self.viewport.sketch.controller.tool
                    if self.names[self.index] in ('Radius', 'Diameter') and 'Radius' in tool.dimensions:
                        value = tool.dimensions['Radius'] * (2 if self.names[self.index] == 'Diameter' else 1)
                        self.input.setText(format(value, '.17g'))
                        self.input.selectAll()
                return True
            if event.key() in (Qt.Key_Return, Qt.Key_Enter):
                if self.accept_value():
                    self.editing = False
                    self.viewport.setFocus()
                    self.viewport.sketch.numeric_commit()
                return True
        return super().eventFilter(watched, event)
