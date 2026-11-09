"""Display and signed-offset input for document construction planes."""
from PySide6.QtWidgets import QDialog, QDialogButtonBox, QFormLayout, QLabel
from vtkmodules.vtkCommonCore import vtkPoints
from vtkmodules.vtkCommonDataModel import vtkCellArray, vtkPolyData
from vtkmodules.vtkRenderingCore import vtkCamera

from hero_cad.ui.dimension_spinbox import DimensionSpinBox
from hero_cad.ui.display_geometry import paths_mesh


def plane_mesh(placements, half_size):
    points, faces = vtkPoints(), vtkCellArray()
    points.SetDataTypeToDouble()
    for frame, center in placements:
        u, v = frame.to_local(center)
        faces.InsertNextCell(4)
        for uv in ((-half_size, -half_size), (half_size, -half_size),
                   (half_size, half_size), (-half_size, half_size)):
            faces.InsertCellPoint(points.InsertNextPoint(*frame.to_world((u + uv[0], v + uv[1]))))
    mesh = vtkPolyData()
    mesh.SetPoints(points)
    mesh.SetPolys(faces)
    return mesh


class ConstructionPlanes:
    def __init__(self, viewport):
        self.viewport = viewport
        self.normal = self.add_layer((.32, .72, .88), .18)
        self.selected = self.add_layer((1., .65, .15), .35)
        self.preview = self.add_layer((.65, .95, .7), .32)
        self.arrow_mapper, self.arrow_actor = viewport.add_actor((.65, .95, .7))
        self.arrow_actor.PickableOff()
        self.arrow_actor.VisibilityOff()
        self.arrow_actor.GetProperty().LightingOff()
        self.arrow_actor.GetProperty().SetLineWidth(2)
        self.state = (None, None, None)

    def add_layer(self, color, opacity):
        mapper, actor = self.viewport.add_actor(color)
        mapper.SetResolveCoincidentTopologyToPolygonOffset()
        mapper.SetRelativeCoincidentTopologyPolygonOffsetParameters(-1, -1)
        actor.PickableOff()
        actor.VisibilityOff()
        prop = actor.GetProperty()
        prop.LightingOff()
        prop.SetOpacity(opacity)
        prop.EdgeVisibilityOn()
        prop.SetEdgeColor(*color)
        return mapper, actor

    @staticmethod
    def half_size(document):
        box = document.parameters
        return max(box.width, box.depth, box.height) * .65

    def prepare(self, document, key):
        selected = key[1] if key and key[0] == 'offset_plane' else None
        frames = tuple((f.id, document.plane_frames[f.id], document.plane_centers[f.id]) for f in document.features
                       if f.type == 'offset_plane' and f.plane_visible and f.id in document.plane_frames)
        selected = selected if any(i == selected for i, _, _ in frames) else None
        size = self.half_size(document) if frames else None
        cache = (frames, selected, size)
        if cache == self.state[0]:
            return self.state
        return (cache, plane_mesh(((frame, center) for i, frame, center in frames if i != selected), size),
                plane_mesh(((frame, center) for i, frame, center in frames if i == selected), size))

    def install(self, state):
        if self.state is state:
            return
        self.state = state
        for (mapper, actor), mesh in zip((self.normal, self.selected), state[1:]):
            mapper.SetInputData(mesh)
            actor.SetVisibility(mesh is not None and mesh.GetNumberOfCells() > 0)

    def recolor(self):
        for (_, actor), key, default in (
                (self.normal, 'sketch.normal', (.32, .72, .88)),
                (self.selected, 'sketch.selected', (1., .65, .15)),
                (self.preview, 'sketch.preview', (.65, .95, .7))):
            color = self.viewport.palette_rgb(key, default)
            actor.GetProperty().SetColor(*color)
            actor.GetProperty().SetEdgeColor(*color)

        self.arrow_actor.GetProperty().SetColor(*self.preview[1].GetProperty().GetColor())

    def set_preview(self, document, frame, center=None, offset=0.):
        mapper, actor = self.preview
        if frame is not None:
            size = self.half_size(document)
            mapper.SetInputData(plane_mesh(((frame, center),), size))
            # Start on the support plane and point along the effective + normal.
            length = size * .5
            normal = frame.normal

            def point(along, across=0.):
                return tuple(c + (along - offset)*n + across*u
                             for c, n, u in zip(center, normal, frame.u))

            tip = point(length)
            self.arrow_mapper.SetInputData(paths_mesh([
                (point(0.), tip),
                (point(length * .7, -length * .18), tip, point(length * .7, length * .18)),
            ]))
        actor.SetVisibility(frame is not None)
        self.arrow_actor.SetVisibility(frame is not None)


def request_offset(window, reference, offset, *, editing=None):
    """Preview a reference frame only; the caller commits one history edit."""
    dialog = QDialog(window)
    dialog.setWindowTitle('Edit Offset Plane' if editing else 'Create Offset Plane')
    form = QFormLayout(dialog)
    field = DimensionSpinBox()
    field.setDecimals(9)
    field.setRange(-100000, 100000)
    field.setSuffix(' mm')
    field.setValue(offset)
    field.setKeyboardTracking(True)
    form.addRow('Signed offset', field)
    form.addRow(QLabel('The preview arrow points toward positive offsets.'))
    feedback = QLabel()
    feedback.setWordWrap(True)
    form.addRow(feedback)
    buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
    buttons.accepted.connect(dialog.accept)
    buttons.rejected.connect(dialog.reject)
    form.addRow(buttons)

    viewport = window.viewport
    display = window.construction_planes
    camera = viewport.renderer.GetActiveCamera()
    saved = vtkCamera()
    saved.DeepCopy(camera)

    def preview(value):
        try:
            _, frame, center = window.document.offset_plane_parameters(reference, value, editing=editing)
        except ValueError as error:
            feedback.setText(str(error))
            buttons.button(QDialogButtonBox.Ok).setEnabled(False)
            display.set_preview(window.document, None)
            viewport.GetRenderWindow().Render()
            return
        feedback.setText('')
        buttons.button(QDialogButtonBox.Ok).setEnabled(True)
        display.set_preview(window.document, frame, center, value)
        viewport.fit()

    field.valueChanged.connect(preview)
    try:
        preview(field.value())
        field.setFocus()
        field.selectAll()
        if dialog.exec():
            return field.value()
        return None
    finally:
        display.set_preview(window.document, None)
        camera.DeepCopy(saved)
        viewport.clamp_zoom()
        viewport.GetRenderWindow().Render()
        dialog.deleteLater()
