"""Small reusable cursor readout/editor; values belong to construction tools only."""
from PySide6.QtCore import Qt, QEvent, QPoint
from PySide6.QtWidgets import QWidget, QVBoxLayout, QLabel, QLineEdit


class ConstructionDimensions(QWidget):
    def __init__(self, viewport):
        super().__init__(viewport)
        self.viewport = viewport
        self.names = []
        self.index = 0
        self.label = QLabel()
        self.input = QLineEdit()
        self.input.setPlaceholderText('Type mm · Tab next · Enter place')
        self.input.installEventFilter(self)
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
        self.setAttribute(Qt.WA_TransparentForMouseEvents, True)

    def reset(self):
        self.input.clear()
        self.input.hide()
        self.hide()
        self.setAttribute(Qt.WA_TransparentForMouseEvents, True)

    def update_values(self, position=None):
        tool = self.viewport.sketch.controller.tool
        values = tool.dimension_values() if tool else {}
        names = list(values)
        if names != self.names:
            self.names, self.index = names, 0
            self.input.clear()
        if not values:
            self.reset()
            return
        self.label.setText(' | '.join(f'{n}: {tool.dimensions.get(n, v):.12g} mm' + (' 🔒' if n in tool.dimensions else '')
                                      for n, v in values.items()) + '\nType mm · Tab next · Enter place · Esc cancel')
        if position is not None:
            self.cursor_position = position.toPoint() if hasattr(position, 'toPoint') else position
        self.adjustSize()
        self.move(max(0, min(self.cursor_position.x()+18, self.viewport.width()-self.width())),
                  max(0, min(self.cursor_position.y()+18, self.viewport.height()-self.height())))
        self.show()
        self.raise_()

    def begin(self, text=''):
        if not self.names:
            return False
        self.input.show()
        self.setAttribute(Qt.WA_TransparentForMouseEvents, False)
        self.input.setPlaceholderText(self.names[self.index] + ' (mm)')
        self.input.setText(text)
        self.input.setFocus()
        self.input.setCursorPosition(len(text))
        self.adjustSize()
        return True

    def accept_value(self):
        try:
            tool = self.viewport.sketch.controller.tool
            if not tool:
                return False
            if self.input.text().strip():
                tool.set_dimension(self.names[self.index], float(self.input.text()))
            elif self.names[self.index] not in tool.dimensions:
                raise ValueError('Enter a positive dimension in mm')
        except (ValueError, OverflowError) as error:
            self.viewport.viewFeedback.emit(str(error))
            self.input.selectAll()
            return False
        self.input.clear()
        self.viewport.sketch.numeric_preview()
        return True

    def eventFilter(self, watched, event):
        if event.type() == QEvent.KeyPress:
            if event.key() == Qt.Key_Escape:
                self.viewport.sketch.set_tool('select')
                self.viewport.setFocus()
                return True
            if event.key() in (Qt.Key_Tab, Qt.Key_Backtab):
                if self.accept_value():
                    self.index = (self.index + ( -1 if event.key() == Qt.Key_Backtab else 1)) % len(self.names)
                    self.input.setPlaceholderText(self.names[self.index] + ' (mm)')
                return True
            if event.key() in (Qt.Key_Return, Qt.Key_Enter):
                if self.accept_value():
                    self.input.hide()
                    self.setAttribute(Qt.WA_TransparentForMouseEvents, True)
                    self.viewport.setFocus()
                    self.viewport.sketch.numeric_commit()
                return True
        return super().eventFilter(watched, event)
