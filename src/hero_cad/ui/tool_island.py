"""Viewport-owned Qt overlay; only explicit user layout changes are persisted."""
from PySide6.QtCore import Qt, QEvent, QPoint, QSize, QSettings, QTimer
from PySide6.QtWidgets import (
    QFrame, QLabel, QToolButton, QComboBox, QScrollArea,
    QWidget, QVBoxLayout, QHBoxLayout, QGridLayout, QSizePolicy,
)


def application_settings():
    return QSettings('HERO-CAD', 'HERO-CAD')


class IslandHeader(QFrame):
    def __init__(self, island):
        super().__init__(island)
        self.island, self.start = island, None
        self.setCursor(Qt.SizeAllCursor)
        self.setToolTip('Drag to move the tool island within the viewport')

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.start = event.globalPosition().toPoint(), self.island.pos()
            event.accept()
        else:
            super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self.start is not None:
            self.island.place(self.start[1] + event.globalPosition().toPoint()-self.start[0])
            event.accept()
        else:
            super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.LeftButton and self.start is not None:
            self.start = None
            self.island.save_layout()
            event.accept()
        else:
            super().mouseReleaseEvent(event)


class ToolIsland(QFrame):
    PRESETS = {'Compact': QSize(212, 300), 'Medium': QSize(292, 352), 'Expanded': QSize(392, 408)}
    PREFIX = 'tool_island/v1/'

    def __init__(self, viewport, registry, *, settings=None, preference_store=None):
        super().__init__(viewport)
        # Preserve one usable command column and the header at the smallest
        # ordinary window size; larger presets can scroll vertically.
        viewport.setMinimumSize(max(viewport.minimumWidth(), 224), max(viewport.minimumHeight(), 180))
        self.registry = registry
        self.settings = settings if settings is not None else application_settings()
        from hero_cad.preferences import Preferences
        self.preference_store = preference_store if preference_store is not None else Preferences(self.settings, self)
        self.context = 'model'
        self.buttons = {}
        self.visible_commands = ()
        self._ready = False
        self.preset = self.preference_store.get(self.PREFIX+'size')
        if not isinstance(self.preset, str) or self.preset not in self.PRESETS:
            self.preset = 'Medium'
        self.collapsed = self.read_bool('collapsed', False)
        self.requested_visible = self.read_bool('visible', True)
        try:
            self.preferred_position = QPoint(int(self.preference_store.get(self.PREFIX+'x')),
                                             int(self.preference_store.get(self.PREFIX+'y')))
        except (ValueError, TypeError, OverflowError):
            self.preferred_position = None
        self.setObjectName('toolIsland')
        self.setAttribute(Qt.WA_StyledBackground)
        self.setAttribute(Qt.WA_AlwaysShowToolTips)
        self.setStyleSheet('''
            QFrame#toolIsland { background: #242e34; border: 1px solid #566d72; border-radius: 6px; }
            QFrame#toolIsland QLabel { color: #bed3d0; background: transparent; border: none; }
            QFrame#toolIsland QToolButton { background: #33434b; color: #dae5e3; border: 1px solid #53666d;
                border-radius: 3px; padding: 5px 4px; }
            QFrame#toolIsland QToolButton:hover { background: #425960; }
            QFrame#toolIsland QToolButton:checked { background: #865227; color: #ffe2b4; border-color: #d39752; }
            QFrame#toolIsland QToolButton:disabled { color: #7e9094; background: #29353c; border-color: #3a4a51; }
            QFrame#toolIsland QComboBox { background: #33434b; color: #dae5e3; padding: 3px; border: 1px solid #53666d; }
            QFrame#toolIsland QScrollArea, QFrame#toolIsland QWidget#toolContents { background: transparent; border: none; }
        ''')
        layout = QVBoxLayout(self)
        layout.setContentsMargins(7, 5, 7, 7)
        layout.setSpacing(5)
        self.header = IslandHeader(self)
        header_layout = QHBoxLayout(self.header)
        header_layout.setContentsMargins(0, 0, 0, 0)
        title = QLabel('HERO Tools')
        title.setAttribute(Qt.WA_TransparentForMouseEvents)
        header_layout.addWidget(title, 1)
        self.collapse_button = QToolButton()
        self.collapse_button.setFixedSize(26, 26)
        self.collapse_button.clicked.connect(lambda: self.set_collapsed(not self.collapsed))
        header_layout.addWidget(self.collapse_button)
        layout.addWidget(self.header)
        self.body = QWidget()
        body_layout = QVBoxLayout(self.body)
        body_layout.setContentsMargins(0, 0, 0, 0)
        body_layout.setSpacing(5)
        row = QHBoxLayout()
        self.context_label = QLabel('Model')
        row.addWidget(self.context_label, 1)
        self.size_choice = QComboBox()
        self.size_choice.addItems(list(self.PRESETS))
        self.size_choice.setCurrentText(self.preset)
        self.size_choice.setAccessibleName('Tool island size')
        self.size_choice.currentTextChanged.connect(self.set_preset)
        row.addWidget(self.size_choice)
        body_layout.addLayout(row)
        self.context_hint = QLabel()
        self.context_hint.setWordWrap(True)
        self.context_hint.setFixedHeight(44)
        self.context_hint.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Fixed)
        body_layout.addWidget(self.context_hint)
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.contents = QWidget()
        self.contents.setObjectName('toolContents')
        self.grid = QGridLayout(self.contents)
        self.grid.setContentsMargins(0, 0, 0, 0)
        self.grid.setSpacing(5)
        self.grid.setAlignment(Qt.AlignTop)
        self.scroll.setWidget(self.contents)
        body_layout.addWidget(self.scroll, 1)
        layout.addWidget(self.body, 1)
        for identifier, command in registry.commands.items():
            if not command.contexts:
                continue
            button = QToolButton(self.contents)
            button.setDefaultAction(command.action)
            button.setToolButtonStyle(Qt.ToolButtonTextOnly)
            button.setMinimumSize(104, 30)
            button.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
            self.buttons[identifier] = button
            button.hide()
        viewport.installEventFilter(self)
        self.set_context('model')
        self.apply_collapsed_state()
        self.setVisible(self.requested_visible)
        QTimer.singleShot(0, self.initialize_position)

    def read_bool(self, name, default):
        return self.preference_store.get(self.PREFIX+name)

    def mousePressEvent(self, event):
        event.accept()

    def mouseMoveEvent(self, event):
        event.accept()

    def mouseReleaseEvent(self, event):
        event.accept()

    def mouseDoubleClickEvent(self, event):
        event.accept()

    def wheelEvent(self, event):
        event.accept()

    def initialize_position(self):
        self._ready = True
        self.apply_geometry()

    def apply_geometry(self):
        if not self._ready:
            return
        viewport = self.parentWidget()
        if self.preferred_position is None and not viewport.isVisible():
            return
        target = QSize(142, 40) if self.collapsed else self.PRESETS[self.preset]
        self.setFixedSize(min(target.width(), max(1, viewport.width()-12)),
                          min(target.height(), max(1, viewport.height()-12)))
        if self.preferred_position is None:
            self.preferred_position = QPoint(max(0, viewport.width()-self.width()-16), 16)
        self.place(self.preferred_position, remember=False)
        self.reflow()
        self.raise_()

    def place(self, position, *, remember=True):
        viewport = self.parentWidget()
        point = QPoint(max(0, min(position.x(), viewport.width()-self.width())),
                       max(0, min(position.y(), viewport.height()-self.height())))
        self.move(point)
        if remember:
            self.preferred_position = QPoint(point)

    def eventFilter(self, watched, event):
        if watched is self.parentWidget() and event.type() in (QEvent.Resize, QEvent.Show):
            self.apply_geometry()
        return super().eventFilter(watched, event)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if hasattr(self, 'grid'):
            self.reflow()

    def reflow(self):
        while self.grid.count():
            self.grid.takeAt(0)
        columns = max(1, min(3, (self.width()-34)//109))
        for i in range(3):
            self.grid.setColumnStretch(i, 1 if i < columns else 0)
        for i, identifier in enumerate(self.visible_commands):
            self.grid.addWidget(self.buttons[identifier], i//columns, i % columns)

    def set_context(self, context, hint=''):
        identifiers = self.registry.for_context(context)
        if identifiers != self.visible_commands:
            for identifier, button in self.buttons.items():
                button.setVisible(identifier in identifiers)
            self.visible_commands = identifiers
            self.reflow()
        self.context = context
        self.context_label.setText({'model': 'Model', 'face': 'Planar face', 'sketch': 'Sketch'}[context])
        self.context_hint.setText(hint)
        self.context_hint.setToolTip(hint)

    def set_preset(self, name):
        if name not in self.PRESETS:
            raise ValueError('Unknown tool island size')
        self.preset = name
        if self.size_choice.currentText() != name:
            self.size_choice.setCurrentText(name)
            return
        self.apply_geometry()
        self.save_layout()

    def apply_collapsed_state(self):
        self.body.setVisible(not self.collapsed)
        self.collapse_button.setText('+' if self.collapsed else '−')
        self.collapse_button.setToolTip('Expand tool island' if self.collapsed else 'Collapse tool island')
        self.collapse_button.setAccessibleName('Expand tool island' if self.collapsed else 'Collapse tool island')
        self.apply_geometry()

    def set_collapsed(self, collapsed):
        self.collapsed = bool(collapsed)
        self.apply_collapsed_state()
        self.save_layout()

    def set_user_visible(self, visible):
        self.requested_visible = bool(visible)
        self.setVisible(self.requested_visible)
        self.raise_()
        self.save_layout()

    def save_layout(self):
        values = {'size': self.preset, 'collapsed': self.collapsed, 'visible': self.requested_visible}
        if self.preferred_position is not None:
            values.update(x=self.preferred_position.x(), y=self.preferred_position.y())
        for key, value in values.items():
            self.preference_store.set(self.PREFIX+key, value)
