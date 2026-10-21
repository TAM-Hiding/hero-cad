from pathlib import Path
from dataclasses import fields as data_fields, replace

from PySide6.QtCore import Qt, QSignalBlocker
from PySide6.QtGui import QAction, QKeySequence
from PySide6.QtWidgets import (
    QComboBox, QLabel, QSpinBox, QStackedWidget, QFileDialog, QDockWidget, QDoubleSpinBox, QFormLayout, QMainWindow, QMessageBox,
    QPushButton, QTreeWidget, QTreeWidgetItem, QWidget,
)
from star_cad import __version__
from star_cad.document import BoxParameters, Document
from star_cad.geometry import volume
from star_cad.sketch import PLANES
from star_cad.ui.viewport import Viewport


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.resize(1200, 780)
        self.document = Document()
        self.entity_context = None
        self.browser_key = None
        self.viewport = Viewport(self)
        self.setCentralWidget(self.viewport)
        self.browser = QTreeWidget()
        self.browser.setHeaderLabel("Model · mm")
        self.box_item = QTreeWidgetItem(self.browser, ["Box"])
        self.browser.setCurrentItem(self.box_item)
        self.add_panel("Model browser", self.browser, Qt.LeftDockWidgetArea)
        panel = QWidget()
        form = QFormLayout(panel)
        self.fields = {}
        for name, label in (("width", "Width · X"), ("depth", "Depth · Y"), ("height", "Height · Z")):
            field = QDoubleSpinBox()
            field.setDecimals(3)
            field.setRange(0.001, 100000)
            field.setSuffix(" mm")
            field.setValue(getattr(self.document.parameters, name))
            field.setKeyboardTracking(False)
            field.valueChanged.connect(self.update_actions)
            self.fields[name] = field
            form.addRow(label, field)
        self.apply_button = QPushButton("Apply dimensions")
        self.apply_button.clicked.connect(self.apply_dimensions)
        form.addRow(self.apply_button)
        self.property_stack = QStackedWidget()
        self.property_stack.addWidget(panel)
        self.entity_panel = QWidget()
        self.entity_form = QFormLayout(self.entity_panel)
        self.entity_fields = {}
        self.property_stack.addWidget(self.entity_panel)
        self.property_info = QLabel("Select an origin plane to create a sketch")
        self.property_info.setWordWrap(True)
        self.property_stack.addWidget(self.property_info)
        self.add_panel("Properties", self.property_stack, Qt.RightDockWidgetArea)
        self.browser.currentItemChanged.connect(self.browser_selection)
        self.browser.itemDoubleClicked.connect(lambda *_: self.edit_sketch())
        toolbar = self.addToolBar("View")
        fit = QAction("Fit all", self)
        fit.setShortcut("F")
        fit.triggered.connect(self.viewport.fit)
        toolbar.addAction(fit)
        self.selection_choice = QComboBox()
        self.selection_choice.addItems(["Select faces", "Select edges"])
        self.selection_choice.setToolTip("Click to select; drag to orbit; Escape clears selection")
        self.selection_choice.currentIndexChanged.connect(
            lambda index: self.viewport.set_selection_mode('face' if index == 0 else 'edge'))
        toolbar.addWidget(self.selection_choice)
        self.pick_radius = QSpinBox()
        self.pick_radius.setRange(2, 10)
        self.pick_radius.setValue(6)
        self.pick_radius.setSuffix(" px")
        self.pick_radius.setToolTip("Edge picking radius; independent of the thin rendered line")
        self.pick_radius.valueChanged.connect(lambda value: setattr(self.viewport, 'edge_tolerance_px', value))
        toolbar.addWidget(self.pick_radius)
        self.view_choice = QComboBox()
        self.view_choice.addItems(["Isometric", "Front", "Top", "Right"])
        self.view_choice.setToolTip("Standard views (select a preset to fit the model)")
        self.view_choice.textActivated.connect(self.viewport.orient)
        toolbar.addWidget(self.view_choice)
        self.axes_action = QAction("Origin Axes", self)
        self.axes_action.setCheckable(True)
        self.axes_action.setChecked(True)
        self.axes_action.setToolTip("World origin axes: X red, Y yellow, Z blue")
        self.axes_action.toggled.connect(self.viewport.sketch.guides.set_axes_visible)
        toolbar.addAction(self.axes_action)
        self.viewport.selectionChanged.connect(lambda _: self.update_status())
        self.new_sketch_action = QAction("New Sketch", self)
        self.new_sketch_action.triggered.connect(self.create_sketch)
        toolbar.addAction(self.new_sketch_action)
        self.edit_sketch_action = QAction("Edit Sketch", self)
        self.edit_sketch_action.triggered.connect(self.edit_sketch)
        toolbar.addAction(self.edit_sketch_action)
        self.addToolBarBreak()
        self.sketch_toolbar = self.addToolBar("Sketch construction")
        self.tool_choice = QComboBox()
        self.tool_choice.addItems(["Select", "Line", "Rectangle", "Circle"])
        self.tool_choice.currentTextChanged.connect(lambda name: self.viewport.sketch.set_tool(name.lower()))
        self.sketch_toolbar.addWidget(self.tool_choice)
        self.grid_action = QAction("Grid", self)
        self.grid_action.setCheckable(True)
        self.grid_action.setChecked(True)
        self.grid_action.setToolTip("Show major and minor grid lines; independent of snapping")
        self.grid_action.toggled.connect(self.viewport.sketch.guides.set_grid_visible)
        self.sketch_toolbar.addAction(self.grid_action)
        self.snap_grid_action = QAction("Snap to Grid", self)
        self.snap_origin_action = QAction("Origin Snap", self)
        self.auto_grid_action = QAction("Auto Grid", self)
        for action, option in ((self.snap_grid_action, 'snap_grid'),
                               (self.snap_origin_action, 'snap_origin'),
                               (self.auto_grid_action, 'automatic')):
            action.setCheckable(True)
            action.setChecked(True)
            action.toggled.connect(lambda checked, name=option: self.viewport.sketch.guides.set_option(name, checked))
            self.sketch_toolbar.addAction(action)
        self.snap_grid_action.setToolTip("Snap construction points within 8 screen pixels to minor grid intersections")
        self.snap_origin_action.setToolTip("Prioritize the local sketch origin within 8 screen pixels, independent of grid snapping")
        self.manual_grid_spacing = QDoubleSpinBox()
        self.manual_grid_spacing.setDecimals(6)
        self.manual_grid_spacing.setRange(0.000001, 100000)
        self.manual_grid_spacing.setValue(1)
        self.manual_grid_spacing.setSuffix(" mm minor")
        self.manual_grid_spacing.setKeyboardTracking(False)
        self.manual_grid_spacing.setToolTip("Manual minor interval; major interval is 10 times this value. Disable Auto Grid to edit.")
        self.manual_grid_spacing.setEnabled(False)
        self.auto_grid_action.toggled.connect(lambda checked: self.manual_grid_spacing.setEnabled(not checked))
        self.manual_grid_spacing.valueChanged.connect(lambda value: self.viewport.sketch.guides.set_option('manual_spacing', value))
        self.sketch_toolbar.addWidget(self.manual_grid_spacing)
        self.finish_sketch_action = QAction("Finish Sketch", self)
        self.finish_sketch_action.triggered.connect(self.finish_sketch)
        self.sketch_toolbar.addAction(self.finish_sketch_action)
        self.sketch_toolbar.hide()
        self.viewport.entityCreated.connect(self.entity_created)
        self.viewport.sketchEntityPicked.connect(self.entity_picked)
        self.viewport.toolHintChanged.connect(lambda _: self.update_status())
        self.viewport.toolChanged.connect(self.sync_tool)
        file_menu = self.menuBar().addMenu("&File")
        self.new_action = self.action(file_menu, "&New", QKeySequence.New, self.new_document)
        self.open_action = self.action(file_menu, "&Open…", QKeySequence.Open, self.open_document)
        self.save_action = self.action(file_menu, "&Save", QKeySequence.Save, self.save_document)
        self.action(file_menu, "Save &As…", QKeySequence.SaveAs, lambda: self.save_document(save_as=True))
        edit_menu = self.menuBar().addMenu("&Edit")
        self.undo_action = self.action(edit_menu, "&Undo", QKeySequence.Undo, self.undo)
        self.redo_action = self.action(edit_menu, "&Redo", QKeySequence.Redo, self.redo)
        self.refresh(fit=True)

    def add_panel(self, title, widget, area):
        dock = QDockWidget(title, self)
        dock.setWidget(widget)
        self.addDockWidget(area, dock)

    def action(self, menu, title, shortcut, callback):
        action = QAction(title, self)
        action.setShortcut(shortcut)
        action.triggered.connect(callback)
        menu.addAction(action)
        return action

    def field_parameters(self):
        for field in self.fields.values():
            field.interpretText()
        return BoxParameters(**{
            n: (f.value() if f.value() != self._shown_values[n]
                else getattr(self.document.parameters, n))
            for n, f in self.fields.items()
        })

    def has_pending_edits(self):
        if self.entity_context:
            return any(f.value() != self.entity_shown[n] for n, f in self.entity_fields.items())
        return hasattr(self, '_shown_values') and any(f.value() != self._shown_values[n] for n, f in self.fields.items())

    def update_actions(self):
        # Signals can arrive while the property panel is being constructed.
        if not hasattr(self, 'undo_action'):
            return
        pending = self.has_pending_edits()
        self.undo_action.setEnabled(pending or self.document.can_undo)
        self.redo_action.setEnabled(not pending and self.document.can_redo)
        active = self.viewport.sketch.active_id is not None
        key = self.browser_key or ()
        self.new_sketch_action.setEnabled(not active and bool(key) and key[0] == 'plane')
        self.edit_sketch_action.setEnabled(not active and bool(key) and key[0] in ('sketch', 'entity'))
        self.sketch_toolbar.setVisible(active)
        self.selection_choice.setEnabled(not active)
        self.view_choice.setEnabled(not active)
        name = self.document.path.name if self.document.path else "Untitled"
        marker = " *" if self.document.dirty or pending else ""
        self.setWindowTitle(f"STAR-CAD {__version__} — {name}{marker}")

    def refresh(self, fit=False):
        for name, field in self.fields.items():
            with QSignalBlocker(field):
                field.setValue(getattr(self.document.parameters, name))
                field.setToolTip(f"Stored dimension: {getattr(self.document.parameters, name):.15g} mm")
        # Preserve untouched loaded values even if the editor displays fewer decimals.
        self._shown_values = {n: f.value() for n, f in self.fields.items()}
        self.viewport.set_shape(self.document.shape, fit=fit)
        self.viewport.sketch.update(self.document.sketches)
        self.viewport.sketch.preview_actor.VisibilityOff()
        if self.viewport.sketch.controller.tool:
            self.viewport.sketch.controller.tool.cancel()
        if self.entity_context:
            try:
                self.current_entity()
            except (StopIteration, AttributeError):
                self.entity_context = None
        self.rebuild_browser()
        self.show_properties()
        if fit:
            self.viewport.fit()
        self.update_status()
        self.update_actions()

    def apply_dimensions(self):
        try:
            if self.entity_context:
                entity = self.current_entity()
                values = self.entity_values()
                self.document.update_entity(self.entity_context[0], replace(entity, **values))
            else:
                self.document.set_box(self.field_parameters())
        except Exception as error:
            QMessageBox.warning(self, "Cannot update parameters", str(error))
            return False
        self.refresh()
        return True

    def undo(self):
        try:
            # Undo first cancels uncommitted property edits.
            if not self.has_pending_edits():
                self.document.undo()
        except Exception as error:
            QMessageBox.warning(self, "Cannot undo", str(error))
            return
        self.refresh()

    def redo(self):
        if self.has_pending_edits():
            return
        try:
            self.document.redo()
        except Exception as error:
            QMessageBox.warning(self, "Cannot redo", str(error))
            return
        self.refresh()

    def save_document(self, checked=False, *, save_as=False):
        path = self.document.path
        if save_as or path is None:
            selected, _ = QFileDialog.getSaveFileName(
                self, "Save STAR-CAD document", str(path or "Untitled.starcad"),
                "STAR-CAD documents (*.starcad)")
            if not selected:
                return False
            path = selected
            if not path.lower().endswith('.starcad'):
                path += '.starcad'
                if Path(path).exists() and QMessageBox.question(
                    self, "Replace file?", f"Replace {path}?",
                    QMessageBox.Yes | QMessageBox.No, QMessageBox.No
                ) != QMessageBox.Yes:
                    return False
        if not self.apply_dimensions():
            return False
        try:
            self.document.save(path)
        except Exception as error:
            QMessageBox.warning(self, "Cannot save document", str(error))
            return False
        self.update_actions()
        return True

    def confirm_replace(self):
        # Commit text to spinbox values before checking staged edits.
        self.field_parameters()
        if self.entity_context:
            self.entity_values()
        if not (self.document.dirty or self.has_pending_edits()):
            return True
        answer = QMessageBox.question(
            self, "Unsaved changes", "Save changes before continuing?",
            QMessageBox.Save | QMessageBox.Discard | QMessageBox.Cancel,
            QMessageBox.Save)
        if answer == QMessageBox.Save:
            return self.save_document()
        return answer == QMessageBox.Discard

    def new_document(self):
        if not self.confirm_replace():
            return
        self.document = Document()
        self.refresh(fit=True)

    def open_document(self):
        selected, _ = QFileDialog.getOpenFileName(
            self, "Open STAR-CAD document", "", "STAR-CAD documents (*.starcad)")
        if not selected:
            return
        try:
            replacement = Document.load(selected)
        except Exception as error:
            QMessageBox.warning(self, "Cannot open document", str(error))
            return
        if not self.confirm_replace():
            return
        try:
            # Saving in the prompt may have changed the selected file itself.
            replacement = Document.load(selected)
        except Exception as error:
            QMessageBox.warning(self, "Cannot open document", str(error))
            return
        self.document = replacement
        self.refresh(fit=True)

    def current_entity(self):
        sketch_id, entity_id = self.entity_context
        return next(e for e in self.document.feature(sketch_id).parameters.entities if e.id == entity_id)

    def entity_values(self):
        entity = self.current_entity()
        for field in self.entity_fields.values():
            field.interpretText()
        return {n: (f.value() if f.value() != self.entity_shown[n] else getattr(entity, n))
                for n, f in self.entity_fields.items()}

    def show_properties(self):
        if self.entity_context:
            while self.entity_form.rowCount():
                self.entity_form.removeRow(0)
            self.entity_fields = {}
            entity = self.current_entity()
            self.entity_form.addRow(QLabel(type(entity).__name__ + " · local sketch coordinates"))
            for parameter in data_fields(entity):
                if parameter.name == 'id':
                    continue
                name = parameter.name
                field = QDoubleSpinBox()
                field.setDecimals(9)
                field.setRange(0.000001 if name in ('width', 'height', 'radius', 'distance') else -1000000, 1000000)
                field.setSuffix(" °" if name == 'angle' else " mm")
                field.setValue(getattr(entity, name))
                field.setToolTip(f"Stored: {getattr(entity, name):.17g}")
                field.setKeyboardTracking(False)
                field.valueChanged.connect(self.update_actions)
                self.entity_fields[name] = field
                self.entity_form.addRow(name.replace('_', ' ').title(), field)
            self.entity_shown = {n: f.value() for n, f in self.entity_fields.items()}
            self.entity_apply = QPushButton("Apply entity parameters")
            self.entity_apply.clicked.connect(self.apply_dimensions)
            self.entity_form.addRow(self.entity_apply)
            self.property_stack.setCurrentIndex(1)
            self.viewport.sketch.select_entity(entity.id)
        elif self.browser_key and self.browser_key[0] != 'box':
            self.property_stack.setCurrentIndex(2)
            self.property_info.setText("Select an Origin plane and choose New Sketch, or select an existing sketch and choose Edit Sketch.")
        else:
            self.property_stack.setCurrentIndex(0)

    def rebuild_browser(self):
        with QSignalBlocker(self.browser):
            self.browser.clear()
            origin = QTreeWidgetItem(self.browser, ["Origin"])
            self.browser_items = {}
            for plane in PLANES:
                item = QTreeWidgetItem(origin, [plane + " Plane"])
                key = ('plane', plane)
                item.setData(0, Qt.UserRole, key)
                self.browser_items[key] = item
            origin.setExpanded(True)
            body = QTreeWidgetItem(self.browser, ["Body 1"])
            for feature in self.document.features:
                status = self.document.statuses[feature.id]
                if feature.type == 'box':
                    item = QTreeWidgetItem(body, ["Box"])
                    self.box_item = item
                    key = ('box', feature.id)
                else:
                    number = len([k for k in self.browser_items if k[0] == 'sketch']) + 1
                    item = QTreeWidgetItem(self.browser, [f"Sketch {number} · {feature.parameters.plane}"])
                    key = ('sketch', feature.id)
                    for i, entity in enumerate(feature.parameters.entities, 1):
                        child = QTreeWidgetItem(item, [f"{type(entity).__name__} {i}"])
                        child_key = ('entity', feature.id, entity.id)
                        child.setData(0, Qt.UserRole, child_key)
                        self.browser_items[child_key] = child
                    item.setExpanded(feature.id == self.viewport.sketch.active_id)
                item.setToolTip(0, "Valid · " + feature.id if status.valid else status.error)
                item.setData(0, Qt.UserRole, key)
                self.browser_items[key] = item
            body.setExpanded(True)
            if self.browser_key not in self.browser_items:
                self.browser_key = next(k for k in self.browser_items if k[0] == 'box')
            self.browser.setCurrentItem(self.browser_items[self.browser_key])

    def browser_selection(self, item, previous):
        key = item.data(0, Qt.UserRole) if item else None
        key = tuple(key) if key else None
        if key == self.browser_key:
            return
        if self.has_pending_edits() and not self.apply_dimensions():
            with QSignalBlocker(self.browser):
                self.browser.setCurrentItem(self.browser_items.get(self.browser_key))
            return
        self.browser_key = key
        with QSignalBlocker(self.browser):
            self.browser.setCurrentItem(self.browser_items.get(key))
        self.entity_context = (key[1], key[2]) if key and key[0] == 'entity' else None
        self.viewport.sketch.select_entity(self.entity_context[1] if self.entity_context else None)
        self.show_properties()
        self.update_actions()

    def create_sketch(self):
        if not self.browser_key or self.browser_key[0] != 'plane':
            return
        plane = self.browser_key[1]
        if self.has_pending_edits() and not self.apply_dimensions():
            return
        try:
            identifier = self.document.add_sketch(plane)
        except Exception as error:
            QMessageBox.warning(self, "Cannot create sketch", str(error))
            return
        self.browser_key = ('sketch', identifier)
        self.refresh()
        self.viewport.sketch.enter(identifier)
        self.update_actions()
        self.update_status()

    def edit_sketch(self):
        key = self.browser_key
        if not key or key[0] not in ('sketch', 'entity') or self.viewport.sketch.active_id:
            return
        if self.has_pending_edits() and not self.apply_dimensions():
            return
        self.viewport.sketch.enter(key[1])
        self.update_actions()
        self.update_status()

    def finish_sketch(self):
        if self.has_pending_edits() and not self.apply_dimensions():
            return
        self.viewport.sketch.finish()
        self.update_actions()
        self.update_status()

    def sync_tool(self, name):
        with QSignalBlocker(self.tool_choice):
            self.tool_choice.setCurrentText(name.title())

    def entity_created(self, entity):
        identifier = self.viewport.sketch.active_id
        if not identifier:
            return
        if self.has_pending_edits() and not self.apply_dimensions():
            return
        try:
            self.document.add_entity(identifier, entity)
        except Exception as error:
            # Construction failures are inline feedback, never placement dialogs.
            self.statusBar().showMessage(str(error))
            return
        self.entity_context = (identifier, entity.id)
        self.browser_key = ('entity', identifier, entity.id)
        self.refresh()

    def entity_picked(self, identifier):
        if identifier is None:
            if self.has_pending_edits() and not self.apply_dimensions():
                return
            self.entity_context = None
            self.browser_key = ('sketch', self.viewport.sketch.active_id)
            with QSignalBlocker(self.browser):
                self.browser.setCurrentItem(self.browser_items.get(self.browser_key))
            self.viewport.sketch.select_entity(None)
            self.show_properties()
            self.update_actions()
            return
        key = ('entity', self.viewport.sketch.active_id, identifier)
        if key in self.browser_items:
            self.browser.setCurrentItem(self.browser_items[key])

    def update_status(self):
        if self.viewport.sketch.active_id:
            self.statusBar().showMessage(self.viewport.sketch.controller.hint + ' | ' + self.viewport.sketch.precision_hint
                                        + " | Middle / Shift-right: Pan | Wheel: Zoom")
            return
        selected = self.viewport.selection
        selection_text = (f"Selected {selected.kind} {selected.index + 1} ({len(self.viewport.selections)} total)  |  "
                          if selected is not None else "")
        self.statusBar().showMessage(
            f"{selection_text}Volume: {volume(self.document.shape):.3f} mm³  |  "
            "Left drag: orbit · middle/Shift-right drag: pan · wheel: zoom · Shift-click: toggle · F: fit"
        )

    def closeEvent(self, event):
        if not self.confirm_replace():
            event.ignore()
            return
        self.viewport.Finalize()
        super().closeEvent(event)
