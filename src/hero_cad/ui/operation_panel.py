"""Modeless analytic operation preview; document changes only on Apply."""
from dataclasses import replace
from math import isfinite
import re
from PySide6.QtCore import Qt, QTimer, QSignalBlocker, QSize
from PySide6.QtGui import QShortcut, QKeySequence
from PySide6.QtWidgets import QDockWidget, QWidget, QFormLayout, QComboBox, QDoubleSpinBox, QPushButton, QLabel, QLineEdit, QHBoxLayout, QScrollArea
from hero_cad.document import Document
from hero_cad.features import Feature, ExtrudeParameters, BooleanParameters
from hero_cad.sketch import new_id
from hero_cad.geometry import compound, volume
from hero_cad.ui.display_geometry import tessellate
from hero_cad.ui.operation_appearance import OPERATION_STYLE, place_operation, fit_operation_size


class OperationScrollArea(QScrollArea):
    """Report the current form hint; scroll only when the screen constrains it."""
    def sizeHint(self):
        return self.widget().sizeHint() if self.widget() is not None else super().sizeHint()


class OperationPanel(QDockWidget):
    def __init__(self, window):
        super().__init__('Operation preview', window)
        self.window = window
        self.setObjectName('operationDialog')
        self.setStyleSheet(OPERATION_STYLE)
        self.active = False
        self.quick_mode = False
        self.chamfer_parameters = None
        self.candidate = None
        self._form_hint = None
        self.preview_timer = QTimer(self)
        self.preview_timer.setSingleShot(True)
        self.preview_timer.setInterval(180)
        self.preview_timer.timeout.connect(self.preview)
        self.open_timer = QTimer(self)
        self.open_timer.setSingleShot(True)
        self.open_timer.timeout.connect(self.finish_opening)
        form = self.form = QFormLayout()
        form.setContentsMargins(10, 8, 10, 8)
        form.setSpacing(6)
        widget = self.surface = QWidget()
        widget.setObjectName('operationSurface')
        widget.setAttribute(Qt.WA_StyledBackground)
        widget.setLayout(form)
        self.scroll = OperationScrollArea()
        self.scroll.setObjectName('operationScroll')
        self.scroll.viewport().setObjectName('operationScrollViewport')
        self.scroll.setWidgetResizable(True)
        self.scroll.setWidget(widget)
        self.setWidget(self.scroll)
        self.operation, self.target = QComboBox(), QComboBox()
        self.target.setSizeAdjustPolicy(QComboBox.AdjustToMinimumContentsLengthWithIcon)
        self.target.setMinimumContentsLength(16)
        self.extent, self.direction = QComboBox(), QComboBox()
        self.extent.addItem('Specified distance','distance')
        self.extent.addItem('Through All (Cut)','through_all')
        self.direction.addItem('Along sketch normal (+)',1)
        self.direction.addItem('Opposite sketch normal (−)',-1)
        self.distance = QDoubleSpinBox()
        self.distance.setDecimals(9)
        self.distance.setRange(-100000,100000)
        self.distance.setSuffix(' mm')
        self.distance.setKeyboardTracking(False)
        self.quick_distance = QLineEdit()
        self.quick_distance.setAccessibleName('Extrusion distance in millimeters')
        self.quick_distance.setToolTip('Signed millimeters: + follows the sketch normal; − reverses direction')
        self.quick_distance.textChanged.connect(self.quick_text_changed)
        self.quick_distance.returnPressed.connect(self.apply_input)
        self.advanced = QPushButton('Advanced…')
        self.advanced.setCheckable(True)
        self.advanced.toggled.connect(lambda _: self.layout_controls())
        self.tools_label = QLabel()
        self.tools_label.setWordWrap(True)
        self.feedback = QLabel('Preview before applying. Negative distance reverses direction.')
        self.feedback.setWordWrap(True)
        form.addRow('Distance · mm',self.quick_distance)
        form.addRow('Operation',self.operation)
        form.addRow('Target body',self.target)
        form.addRow('Tool bodies',self.tools_label)
        form.addRow('Extent',self.extent)
        form.addRow('Signed distance',self.distance)
        form.addRow('Through All direction',self.direction)
        self.preview_button = QPushButton('Preview result')
        self.apply_button = QPushButton('Apply')
        self.apply_button.setProperty('operationRole', 'primary')
        self.cancel_button = QPushButton('Cancel')
        form.addRow(self.advanced)
        form.addRow(self.feedback)
        buttons = QWidget()
        row = QHBoxLayout(buttons)
        row.setContentsMargins(0,0,0,0)
        for button in (self.preview_button,self.cancel_button,self.apply_button):
            row.addWidget(button)
        form.addRow(buttons)
        self.preview_button.clicked.connect(self.preview)
        self.apply_button.clicked.connect(self.apply_input)
        self.cancel_button.clicked.connect(self.cancel)
        self.operation.currentIndexChanged.connect(self.changed)
        for field in (self.target,self.extent,self.direction):
            field.currentIndexChanged.connect(self.invalidate)
        self.distance.valueChanged.connect(self.spin_distance_changed)
        self.mapper,self.actor = window.viewport.add_actor((1.,.65,.15))
        self.actor.GetProperty().SetOpacity(.8)
        self.actor.PickableOff()
        self.actor.VisibilityOff()
        window.addDockWidget(Qt.RightDockWidgetArea,self)
        self.escape = QShortcut(QKeySequence(Qt.Key_Escape),self)
        self.escape.setContext(Qt.WidgetWithChildrenShortcut)
        self.escape.activated.connect(self.cancel)
        self.layout_controls()
        self.hide()

    def open(self, *, source=None, bodies=(), feature=None, quick=False):
        self.cancel()
        self.chamfer_parameters = None
        self.quick_distance.setAccessibleName('Extrusion distance in millimeters')
        self.quick_distance.setToolTip('Signed millimeters: + follows the sketch normal; − reverses direction')
        self.quick_mode = False
        self.source, self.bodies, self.edit_id = source, tuple(bodies), feature.id if feature else None
        self.active = False
        self.operation.clear()
        for text,key in ([('New Body','new')] if source else []) + [('Join','join'),('Cut','cut'),('Intersect','intersect')]:
            self.operation.addItem(text,key)
        d = self.window.document
        eligible = set(d.active_body_ids)
        if source and not feature and not self.window.show_base_box.isChecked():
            eligible = {i for i in eligible if d.feature(i).type != 'box'}
        if feature:
            eligible.update(ref for ref in feature.references if d.feature(ref).type != 'sketch')
            prior = {f.id for f in d.features[:d.features.index(feature)]}
            eligible.intersection_update(prior)
        if bodies:
            eligible.intersection_update(bodies)
        self.target.clear()
        for f in d.features:
            if f.id in eligible:
                self.target.addItem(self.window.body_label(f.id),f.id)
        self.feature_id = feature.id if feature else Feature('extrude',ExtrudeParameters(*source)).id if source else Feature('boolean',BooleanParameters('join',bodies[0],tuple(bodies[1:]))).id
        if feature:
            p = feature.parameters
            self.operation.setCurrentIndex(self.operation.findData(p.operation))
            self.target.setCurrentIndex(self.target.findData(p.target_id))
            if source:
                self.distance.setValue(p.distance)
                self.extent.setCurrentIndex(self.extent.findData(p.extent))
                self.direction.setCurrentIndex(self.direction.findData(p.direction))
        else:
            self.distance.setValue(10)
            self.extent.setCurrentIndex(0)
            self.direction.setCurrentIndex(1)
            if source:
                sketch = d.feature(source[0])
                attachment = sketch.parameters.attachment
                # Only the explicit, resolved attachment owner is evidence of
                # intent. Never substitute a historical owner's successor or
                # infer a target from body order/proximity. Preview still
                # validates the actual Join before anything can be committed.
                if (attachment is not None and d.statuses[sketch.id].valid
                        and attachment.parent_id in eligible):
                    self.operation.setCurrentIndex(self.operation.findData('join'))
                    self.target.setCurrentIndex(self.target.findData(attachment.parent_id))
        self.quick_mode = bool(quick and source and not feature)
        with QSignalBlocker(self.quick_distance):
            self.quick_distance.setText(format(self.distance.value(),'.15g'))
        self.advanced.setChecked(False)
        self.active = True
        self.setWindowTitle('Extrude' if source else 'Combine')
        self.changed()
        self.present()

    def open_chamfer(self, parameters, *, feature=None):
        """Use the existing candidate-document preview actor and commit path."""
        self.cancel()
        self.chamfer_parameters = parameters
        self.source, self.bodies = None, (parameters.target_id,)
        self.edit_id = feature.id if feature else None
        self.feature_id = feature.id if feature else new_id()
        self.quick_mode = True
        with QSignalBlocker(self.quick_distance):
            self.quick_distance.setText(format(parameters.distance, '.17g'))
        self.quick_distance.setAccessibleName('Chamfer distance in millimeters')
        self.quick_distance.setToolTip('Positive equal distance on the two adjacent faces, in millimeters')
        self.tools_label.setText(self.window.body_label(parameters.target_id))
        self.active = True
        self.setWindowTitle('Chamfer')
        self.invalidate()
        self.present()

    def requested_size(self):
        hint = self.sizeHint()
        hint.setWidth(350 if self.quick_mode else min(520, max(350, hint.width())))
        return hint

    def present(self):
        self.setFloating(True)
        self.setWindowModality(Qt.NonModal)
        self.show()
        self.raise_()
        place_operation(self, self.window.tool_island, self.requested_size())
        # Finalize once after Qt has laid out and styled the native window.
        # No island move/resize signal is connected to this window.
        self.open_timer.start(0)

    def finish_opening(self):
        if self.active and self.isVisible() and self.isFloating():
            self._form_hint = self.requested_size()
            place_operation(self, self.window.tool_island, self._form_hint)
            self.focus_distance()

    def resize_visible_form(self):
        if self.active and self.isVisible() and self.isFloating():
            hint = self.requested_size()
            if hint != self._form_hint:
                self._form_hint = QSize(hint)
                # Respect a manually resized width; only adapt to changed form
                # content, not every keystroke/validation signal.
                hint.setWidth(self.width())
                fit_operation_size(self, hint, self.screen().availableGeometry())

    def changed(self, *_):
        if not self.active:
            return
        op = self.operation.currentData()
        self.target.setEnabled(op != 'new')
        self.extent.setEnabled(bool(self.source) and op == 'cut')
        self.distance.setEnabled(bool(self.source) and self.extent.currentData() != 'through_all')
        self.direction.setEnabled(bool(self.source) and op == 'cut' and self.extent.currentData() == 'through_all')
        self.layout_controls()
        self.invalidate()

    def invalidate(self, *_):
        if not self.active:
            return
        if self.chamfer_parameters is not None:
            had_preview = bool(self.actor.GetVisibility())
            self.preview_timer.stop()
            self.candidate = None
            self.actor.VisibilityOff()
            self.apply_button.setEnabled(False)
            self.feedback_text('One straight edge · equal distance. Preview or Apply to evaluate.')
            if had_preview:
                self.window.display_solids()
            try:
                self.input_distance()
            except ValueError as error:
                self.feedback_text(str(error))
            else:
                self.apply_button.setEnabled(True)
            self.layout_controls()
            self.window.viewport.GetRenderWindow().Render()
            return
        self.layout_controls()
        had_preview = bool(self.actor.GetVisibility())
        self.preview_timer.stop()
        self.candidate = None
        self.tools_label.setText('Extruded sketch profile' if self.source else ', '.join(
            self.window.body_label(i) for i in self.bodies if i != self.target.currentData()))
        self.apply_button.setEnabled(False)
        self.feedback_text('Preview updated values before Apply. Signed distance: + follows the sketch normal, − reverses it.')
        self.distance.setEnabled(bool(self.source) and not (self.operation.currentData() == 'cut' and self.extent.currentData() == 'through_all'))
        self.direction.setEnabled(bool(self.source) and self.operation.currentData() == 'cut' and self.extent.currentData() == 'through_all')
        self.actor.VisibilityOff()
        if not self.quick_mode or had_preview:
            self.window.display_solids()
            self.window.viewport.sketch.update(self.window.viewport.sketch.features)
            self.window.viewport.GetRenderWindow().Render()
        if self.quick_mode:
            try:
                self.input_distance()
            except ValueError as error:
                self.feedback_text(str(error))
            else:
                self.apply_button.setEnabled(True)
                self.preview_timer.start()

    def feedback_text(self, text):
        self.feedback.setText(text)
        self.feedback.setToolTip(text)
        if self.quick_mode:
            self.layout_controls()

    def layout_controls(self):
        chamfer = self.chamfer_parameters is not None
        self.form.setRowVisible(self.operation, not chamfer)
        self.form.labelForField(self.tools_label).setText('Target body' if chamfer else 'Tool bodies')
        if chamfer:
            for field in (self.distance, self.advanced, self.extent, self.direction, self.target):
                self.form.setRowVisible(field, False)
            self.form.setRowVisible(self.quick_distance, True)
            self.form.setRowVisible(self.tools_label, True)
            self.quick_distance.setEnabled(True)
            self.preview_button.setVisible(True)
            self.feedback.setMaximumWidth(320)
            self.feedback.setMaximumHeight(80)
            self.resize_visible_form()
            return
        quick = self.quick_mode
        advanced = not quick or self.advanced.isChecked()
        self.form.setRowVisible(self.quick_distance,quick)
        self.form.setRowVisible(self.distance,not quick)
        self.form.setRowVisible(self.tools_label,not quick)
        self.form.setRowVisible(self.advanced,quick)
        self.form.setRowVisible(self.extent,advanced)
        self.form.setRowVisible(self.direction,advanced)
        self.form.setRowVisible(self.target,not quick or self.operation.currentData() != 'new')
        self.preview_button.setVisible(advanced)
        self.feedback.setMaximumWidth(320 if quick else 16777215)
        self.feedback.setMaximumHeight(80 if quick else 16777215)
        if hasattr(self,'source'):
            self.quick_distance.setEnabled(bool(self.source) and not (
                self.operation.currentData() == 'cut' and self.extent.currentData() == 'through_all'))
        self.resize_visible_form()

    def focus_distance(self):
        if self.active:
            self.activateWindow()
            field = self.quick_distance if self.quick_mode else self.distance if self.distance.isEnabled() else self.operation
            field.setFocus(Qt.OtherFocusReason)
            if hasattr(field, 'selectAll'):
                field.selectAll()

    def input_distance(self):
        if not self.quick_mode or (self.chamfer_parameters is None and self.operation.currentData() == 'cut' and self.extent.currentData() == 'through_all'):
            return self.distance.value()
        text = self.quick_distance.text().strip()
        if not re.fullmatch(r'[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?',text):
            raise ValueError('Enter a signed distance in mm.')
        value = float(text)
        if self.chamfer_parameters is not None and (not isfinite(value) or not 1e-6 <= value <= 100000):
            raise ValueError('Chamfer distance must be positive, from 0.000001 to 100000 mm.')
        if not isfinite(value) or not 1e-6 <= abs(value) <= 100000:
            raise ValueError('Distance must be nonzero, from ±0.000001 to ±100000 mm.')
        return value

    def quick_text_changed(self, *_):
        if not self.quick_mode or not self.active:
            return
        try:
            value = self.input_distance()
            with QSignalBlocker(self.distance):
                self.distance.setValue(value)
        except ValueError:
            pass
        self.invalidate()

    def spin_distance_changed(self, value):
        if self.quick_mode:
            with QSignalBlocker(self.quick_distance):
                self.quick_distance.setText(format(value,'.15g'))
        self.invalidate()

    def apply_input(self):
        self.preview_timer.stop()
        if not self.quick_mode:
            return self.commit()
        try:
            self.input_distance()
        except ValueError as error:
            self.feedback_text(str(error))
            self.focus_distance()
            return False
        if self.candidate is None or self.window.document.features != self.baseline:
            if not self.preview():
                self.focus_distance()
                return False
        return self.commit()

    def definition(self):
        if self.chamfer_parameters is not None:
            p = replace(self.chamfer_parameters, distance=self.input_distance())
            return Feature('chamfer', p, (p.target_id,), self.feature_id)
        op,target = self.operation.currentData(),self.target.currentData()
        if op != 'new' and target is None:
            raise ValueError('Select an available target body for this operation.')
        if self.source:
            from hero_cad.profiles import resolve_region
            line_ids = (self.window.document.feature(self.edit_id).parameters.line_ids if self.edit_id else
                        resolve_region(self.window.document.feature(self.source[0]).parameters,
                                       self.source[1], self.source[2]).line_ids)
            p = ExtrudeParameters(*self.source,self.input_distance(),op,
                                  None if op == 'new' else target,
                                  self.extent.currentData() if op == 'cut' else 'distance',self.direction.currentData(), line_ids)
            refs = (p.sketch_id,) + ((p.target_id,) if p.target_id else ())
            return Feature('extrude',p,refs,self.feature_id)
        tools = tuple(i for i in self.bodies if i != target)
        p = BooleanParameters(op,target,tools)
        return Feature('boolean',p,(target,*tools),self.feature_id)

    def preview(self):
        self.preview_timer.stop()
        if not self.active:
            return False
        self.candidate = None
        self.apply_button.setEnabled(False)
        self.actor.VisibilityOff()
        try:
            feature = self.definition()
            d = self.window.document
            features = tuple(feature if f.id == self.edit_id else f for f in d.features)
            if not self.edit_id:
                features += (feature,)
            candidate = Document(features=features)
            if not candidate.statuses[feature.id].valid:
                raise ValueError(candidate.statuses[feature.id].error)
            # Preview every resulting body; no old opaque target underneath.
            shapes = [candidate.solid_shapes[i] for i in candidate.active_body_ids
                      if self.window.show_base_box.isChecked() or candidate.feature(i).type != 'box']
            self.mapper.SetInputData(tessellate(compound(shapes)))
            self.window.viewport.set_shape(compound(()))
            self.actor.VisibilityOn()
            self.window.viewport.clamp_zoom()
            self.window.viewport.GetRenderWindow().Render()
            self.candidate,self.baseline = candidate,d.features
            unresolved = sum(not s.valid for s in candidate.statuses.values())
            self.feedback_text(f'Result preview · {len(candidate.active_body_ids)} current body/bodies · {volume(candidate.shape):.9g} mm³'
                                  + (f' · {unresolved} unresolved dependent feature(s); see browser after Apply' if unresolved else ''))
            self.apply_button.setEnabled(True)
            return True
        except Exception as error:
            self.window.display_solids()
            self.feedback_text(str(error))
            self.window.statusBar().showMessage(str(error),6000)
            return False

    def commit(self):
        if self.candidate is None or self.window.document.features != self.baseline:
            self.feedback_text('Document changed or no valid preview; preview again')
            self.apply_button.setEnabled(False)
            return False
        feature = self.definition()
        try:
            features = self.candidate.features
            if (feature.type == 'extrude' and not any(f.id == feature.id for f in self.baseline)
                    and self.window.auto_hide_sketches.isChecked()):
                features = tuple(replace(f, sketch_visible=False)
                                 if f.id == feature.parameters.sketch_id else f for f in features)
            self.window.document.set_features(features)
        except Exception as error:
            self.feedback_text(str(error))
            return False
        self.preview_timer.stop()
        self.active = False
        self.candidate = None
        self.apply_button.setEnabled(False)
        self.actor.VisibilityOff()
        self.hide()
        w = self.window
        if w.viewport.sketch.active_id:
            w.viewport.sketch.finish()
        w.profile_action.setChecked(False)
        w.entity_context = (feature.type,feature.id) if feature.type in ('extrude', 'chamfer') else None
        w.browser_key = (feature.type,feature.id)
        w.refresh(fit=True)
        w.activateWindow()
        w.viewport.setFocus(Qt.OtherFocusReason)
        return True

    def cancel(self, *_):
        self.open_timer.stop()
        self.preview_timer.stop()
        self.actor.VisibilityOff()
        was_active,self.active = self.active,False
        self.candidate = None
        self.apply_button.setEnabled(False)
        self.hide()
        if was_active:
            self.window.profile_action.setChecked(False)
            self.window.viewport.profiles.set_mode(False)
            self.window.display_solids()
            self.window.viewport.sketch.update(self.window.viewport.sketch.features)
            self.window.viewport.GetRenderWindow().Render()
            self.window.update_actions()
            self.window.activateWindow()
            self.window.viewport.setFocus(Qt.OtherFocusReason)

    def closeEvent(self,event):
        self.cancel()
        super().closeEvent(event)
