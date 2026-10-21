"""One parametric box, local file persistence and parameter undo/redo (mm)."""
from dataclasses import asdict, dataclass
import json
from math import isfinite
import os
from pathlib import Path
import tempfile

from star_cad.geometry import make_box


@dataclass(frozen=True)
class BoxParameters:
    width: float = 40.0  # X
    depth: float = 30.0  # Y
    height: float = 20.0  # Z

    def __post_init__(self):
        for value in (self.width, self.depth, self.height):
            if type(value) not in (int, float) or not isfinite(value) or not 0.001 <= value <= 100000:
                raise ValueError("Dimensions must be finite numbers between 0.001 and 100000 mm")


class Document:
    def __init__(self, parameters=None):
        self.parameters = parameters if parameters is not None else BoxParameters()
        self.shape = make_box(**asdict(self.parameters))
        self.path = None
        self._saved_parameters = self.parameters
        self._undo = []
        self._redo = []

    @property
    def dirty(self):
        return self.parameters != self._saved_parameters

    @property
    def can_undo(self):
        return bool(self._undo)

    @property
    def can_redo(self):
        return bool(self._redo)

    def set_box(self, parameters: BoxParameters):
        if parameters == self.parameters:
            return
        shape = make_box(**asdict(parameters))
        self._undo.append(self.parameters)
        self._redo.clear()
        self.parameters, self.shape = parameters, shape

    def undo(self):
        self._restore(self._undo, self._redo)

    def redo(self):
        self._restore(self._redo, self._undo)

    def _restore(self, source, destination):
        if not source:
            return
        parameters = source[-1]
        shape = make_box(**asdict(parameters))
        destination.append(self.parameters)
        source.pop()
        self.parameters, self.shape = parameters, shape

    def save(self, path):
        """Replace only after a complete, flushed file exists in the same directory."""
        path = Path(path).expanduser().absolute()
        payload = {"format": "star-cad", "version": 1, "units": "mm",
                   "box": asdict(self.parameters)}
        temporary = None
        try:
            with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=path.parent,
                                             prefix=f".{path.name}.", suffix=".tmp", delete=False) as stream:
                temporary = Path(stream.name)
                json.dump(payload, stream, indent=2, allow_nan=False)
                stream.write("\n")
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, path)
        finally:
            if temporary is not None:
                temporary.unlink(missing_ok=True)
        self.path = path
        self._saved_parameters = self.parameters

    @classmethod
    def load(cls, path):
        """Validate format and regenerate before the caller replaces its document."""
        path = Path(path).expanduser().absolute()
        with path.open("rb") as stream:
            # A one-box document is tiny; bound input before parsing it.
            contents = stream.read(65537)
        if len(contents) > 65536:
            raise ValueError("Document exceeds the 64 KiB format limit")
        def unique_object(pairs):
            result = {}
            for key, value in pairs:
                if key in result:
                    raise ValueError(f"Duplicate document field: {key}")
                result[key] = value
            return result
        data = json.loads(contents.decode("utf-8"), object_pairs_hook=unique_object)
        if not isinstance(data, dict) or set(data) != {"format", "version", "units", "box"}:
            raise ValueError("Invalid STAR-CAD document fields")
        if data['format'] != 'star-cad' or type(data['version']) is not int or data['version'] != 1:
            raise ValueError("Unsupported STAR-CAD document format/version")
        if data['units'] != 'mm':
            raise ValueError("Only millimetre documents are supported")
        box = data['box']
        if not isinstance(box, dict) or set(box) != {'width', 'depth', 'height'}:
            raise ValueError("Invalid box parameters")
        document = cls(BoxParameters(**box))
        document.path = path
        return document
