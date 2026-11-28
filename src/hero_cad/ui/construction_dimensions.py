"""Small reusable cursor readout/editor; values belong to construction tools only."""
from PySide6.QtCore import Qt, QEvent, QPoint, QPointF, QRect
from PySide6.QtGui import QMouseEvent
from PySide6.QtWidgets import QWidget, QVBoxLayout, QLabel, QLineEdit, QGraphicsOpacityEffect, QApplication
from hero_cad.ui.operation_appearance import INLINE_STYLE
from hero_cad.ui.dimension_spinbox import format_dimension


class ConstructionDimensions(QWidget):
    def __init__(self, viewport):
        super().__init__(viewport)
        self.setObjectName('constructionDimensions')
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
        self.label.setWordWrap(True)
        self.input = QLineEdit()
        self.input.setPlaceholderText('Type mm · Tab next · Enter place')
        self.input.installEventFilter(self)
        for widget in (self, self.label):
            widget.installEventFilter(self)
        for widget in (self, self.label, self.input):
            widget.setMouseTracking(True)
        self.input.textEdited.connect(self.preview_text)
        self.input.hide()
        layout = QVBoxLayout(self)
        layout.setContentsMargins(6, 4, 6, 4)
        layout.addWidget(self.label)
        layout.addWidget(self.input)
        self.setAttribute(Qt.WA_StyledBackground, True)
        self.setStyleSheet(INLINE_STYLE)
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

    def update_values(self, position=None, modifiers=None):
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
        self.label.setText(' | '.join(f'{n}: {format_dimension(tool.dimensions.get(n, v), self.locale())} mm' + (' 🔒' if self.parameter_name(n) in tool.dimensions else '')
                                      for n, v in values.items()) + '\nTab to edit · Ctrl-click field · Enter place · Esc cancel')
        if stage_changed or self.width() > self.viewport.width():
            # Reserve one stable readout footprint for the stage. Changing digit
            # widths must not make the editor oscillate against a viewport edge.
            width = min(360,self.viewport.width())
            margins = self.layout().contentsMargins()
            text = ' | '.join(n+': 1000000.999999999 mm 🔒' for n in names)
            text += '\nTab to edit · Ctrl-click field · Enter place · Esc cancel'
            available = max(1,width-margins.left()-margins.right())
            height = self.label.fontMetrics().boundingRect(QRect(0,0,available,10000),Qt.TextWordWrap,text).height()
            self.setFixedSize(width,height+self.input.sizeHint().height()+self.layout().spacing()+margins.top()+margins.bottom())
        self.input.show()
        if not self.editing:
            self.input.setPlaceholderText(self.names[self.index] + ' (mm) — click or type to enter')
        # Re-anchor per stage, then move only when the drawing cursor approaches.
        # Tab/typing enters stationary numeric mode; Ctrl permits a mouse entry.
        if position is not None and self.anchor_pending and not self.editing:
            self.cursor_position = position.toPoint() if hasattr(position, 'toPoint') else position
            self.anchor_pending = False
        if not self.editing:
            self.adjustSize()
            self.move(max(0, min(self.cursor_position.x()+98, self.viewport.width()-self.width())),
                      max(0, min(self.cursor_position.y()+68, self.viewport.height()-self.height())))
            # Retain a viewport-clamped anchor when a later value gets shorter.
            self.cursor_position = self.pos()-QPoint(98,68)
            if position is not None:
                self.avoid_cursor(position.toPoint() if hasattr(position, 'toPoint') else position,
                                  QApplication.keyboardModifiers() if modifiers is None else modifiers)
        else:
            # Numeric entry stays pinned, except when a smaller viewport would
            # make the field inaccessible. Never re-anchor it to the cursor.
            self.move(max(0, min(self.x(), self.viewport.width()-self.width())),
                      max(0, min(self.y(), self.viewport.height()-self.height())))
        self.setVisible(self.opacity > 0)
        self.raise_()

    def avoid_cursor(self, point, modifiers):
        if self.editing or modifiers & Qt.ControlModifier or not self.geometry().adjusted(-14,-14,14,14).contains(point):
            return
        width, height = self.width(), self.height()
        positions = (QPoint(point.x()+40, point.y()+40),
                     QPoint(point.x()-width-40, point.y()+40),
                     QPoint(point.x()+40, point.y()-height-40),
                     QPoint(point.x()-width-40, point.y()-height-40))
        candidates = []
        for position in positions:
            position = QPoint(max(0,min(position.x(),self.viewport.width()-width)),
                              max(0,min(position.y(),self.viewport.height()-height)))
            if not QRect(position,self.size()).adjusted(-14,-14,14,14).contains(point):
                candidates.append(position)
        if candidates:
            destination = min(candidates,key=lambda p:(p-self.pos()).manhattanLength())
            self.move(destination)
            self.cursor_position = destination-QPoint(98,68)

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
        if (event.type() == QEvent.MouseMove and not self.editing
                and not event.modifiers() & Qt.ControlModifier and self.viewport.sketch.controller.tool):
            # A fast cursor jump can land on a native popup child before the
            # viewport sees a move. Relocate and route that same drawing input.
            local = self.viewport.mapFromGlobal(event.globalPosition().toPoint())
            self.avoid_cursor(local,event.modifiers())
            forwarded = QMouseEvent(QEvent.MouseMove,QPointF(local),event.globalPosition(),
                                    event.button(),event.buttons(),event.modifiers())
            QApplication.sendEvent(self.viewport,forwarded)
            return True
        if watched is not self.input:
            return super().eventFilter(watched,event)
        if event.type() == QEvent.MouseButtonPress and event.button() == Qt.LeftButton and not self.editing:
            self.begin(self.input.text())
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
