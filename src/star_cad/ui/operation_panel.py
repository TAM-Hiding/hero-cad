"""Modeless analytic operation preview; document changes only on Apply."""
from dataclasses import replace
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QDockWidget, QWidget, QFormLayout, QComboBox, QDoubleSpinBox, QPushButton, QLabel
from star_cad.document import Document
from star_cad.features import Feature, ExtrudeParameters, BooleanParameters
from star_cad.geometry import compound, volume
from star_cad.ui.display_geometry import tessellate


class OperationPanel(QDockWidget):
    def __init__(self, window):
        super().__init__('Operation preview', window)
        self.window = window
        self.active = False
        self.candidate = None
        form = QFormLayout()
        widget = QWidget()
        widget.setLayout(form)
        self.setWidget(widget)
        self.operation, self.target = QComboBox(), QComboBox()
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
        self.tools_label = QLabel()
        self.tools_label.setWordWrap(True)
        self.feedback = QLabel('Preview before applying. Negative distance reverses direction.')
        self.feedback.setWordWrap(True)
        form.addRow('Operation',self.operation)
        form.addRow('Target body',self.target)
        form.addRow('Tool bodies',self.tools_label)
        form.addRow('Extent',self.extent)
        form.addRow('Signed distance',self.distance)
        form.addRow('Through All direction',self.direction)
        self.preview_button = QPushButton('Preview result')
        self.apply_button = QPushButton('Apply')
        self.cancel_button = QPushButton('Cancel')
        form.addRow(self.feedback)
        for button in (self.preview_button,self.apply_button,self.cancel_button):
            form.addRow(button)
        self.preview_button.clicked.connect(self.preview)
        self.apply_button.clicked.connect(self.commit)
        self.cancel_button.clicked.connect(self.cancel)
        self.operation.currentIndexChanged.connect(self.changed)
        for field in (self.target,self.extent,self.direction):
            field.currentIndexChanged.connect(self.invalidate)
        self.distance.valueChanged.connect(self.invalidate)
        self.mapper,self.actor = window.viewport.add_actor((1.,.65,.15))
        self.actor.GetProperty().SetOpacity(.8)
        self.actor.PickableOff()
        self.actor.VisibilityOff()
        window.addDockWidget(Qt.RightDockWidgetArea,self)
        self.hide()

    def open(self, *, source=None, bodies=(), feature=None):
        self.cancel()
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
        self.active = True
        self.changed()
        self.show()
        self.raise_()

    def changed(self, *_):
        if not self.active:
            return
        op = self.operation.currentData()
        self.target.setEnabled(op != 'new')
        self.extent.setEnabled(bool(self.source) and op == 'cut')
        self.distance.setEnabled(bool(self.source) and self.extent.currentData() != 'through_all')
        self.direction.setEnabled(bool(self.source) and op == 'cut' and self.extent.currentData() == 'through_all')
        self.invalidate()

    def invalidate(self, *_):
        if not self.active:
            return
        self.candidate = None
        self.tools_label.setText('Extruded sketch profile' if self.source else ', '.join(
            self.window.body_label(i) for i in self.bodies if i != self.target.currentData()))
        self.apply_button.setEnabled(False)
        self.feedback.setText('Preview updated values before Apply. Signed distance: + follows the sketch normal, − reverses it.')
        self.distance.setEnabled(bool(self.source) and not (self.operation.currentData() == 'cut' and self.extent.currentData() == 'through_all'))
        self.direction.setEnabled(bool(self.source) and self.operation.currentData() == 'cut' and self.extent.currentData() == 'through_all')
        self.actor.VisibilityOff()
        self.window.display_solids()
        self.window.viewport.sketch.update(self.window.viewport.sketch.features)
        self.window.viewport.GetRenderWindow().Render()

    def definition(self):
        op,target = self.operation.currentData(),self.target.currentData()
        if self.source:
            p = ExtrudeParameters(*self.source,self.distance.value(),op,
                                  None if op == 'new' else target,
                                  self.extent.currentData() if op == 'cut' else 'distance',self.direction.currentData())
            refs = (p.sketch_id,) + ((p.target_id,) if p.target_id else ())
            return Feature('extrude',p,refs,self.feature_id)
        tools = tuple(i for i in self.bodies if i != target)
        p = BooleanParameters(op,target,tools)
        return Feature('boolean',p,(target,*tools),self.feature_id)

    def preview(self):
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
            self.feedback.setText(f'Result preview · {len(candidate.active_body_ids)} current body/bodies · {volume(candidate.shape):.9g} mm³'
                                  + (f' · {unresolved} unresolved dependent feature(s); see browser after Apply' if unresolved else ''))
            self.apply_button.setEnabled(True)
            return True
        except Exception as error:
            self.window.display_solids()
            self.feedback.setText(str(error))
            self.window.statusBar().showMessage(str(error),6000)
            return False

    def commit(self):
        if self.candidate is None or self.window.document.features != self.baseline:
            self.feedback.setText('Document changed or no valid preview; preview again')
            self.apply_button.setEnabled(False)
            return False
        feature = self.definition()
        try:
            self.window.document.set_features(self.candidate.features)
        except Exception as error:
            self.feedback.setText(str(error))
            return False
        self.active = False
        self.actor.VisibilityOff()
        self.hide()
        w = self.window
        if w.viewport.sketch.active_id:
            w.viewport.sketch.finish()
        w.profile_action.setChecked(False)
        w.entity_context = ('extrude',feature.id) if feature.type == 'extrude' else None
        w.browser_key = (feature.type,feature.id)
        w.refresh(fit=True)
        return True

    def cancel(self, *_):
        self.actor.VisibilityOff()
        was_active,self.active = self.active,False
        self.candidate = None
        self.hide()
        if was_active:
            self.window.display_solids()
            self.window.viewport.sketch.update(self.window.viewport.sketch.features)
            self.window.viewport.GetRenderWindow().Render()

    def closeEvent(self,event):
        self.cancel()
        super().closeEvent(event)
