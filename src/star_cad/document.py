"""One parametric feature for M0; millimetres throughout.

Parameters are authoritative. A replacement solid is built before committing an
edit, so a failed regeneration cannot corrupt the current document.
"""
from dataclasses import dataclass
from math import isfinite

from star_cad.geometry import make_box


@dataclass(frozen=True)
class BoxParameters:
    width: float = 40.0  # X
    depth: float = 30.0  # Y
    height: float = 20.0  # Z

    def __post_init__(self):
        for value in (self.width, self.depth, self.height):
            if not isfinite(value) or not 0.001 <= value <= 100000:
                raise ValueError("Dimensions must be finite and between 0.001 and 100000 mm")


class Document:
    def __init__(self):
        self.parameters = BoxParameters()
        self.shape = make_box(**vars(self.parameters))

    def set_box(self, parameters: BoxParameters):
        shape = make_box(**vars(parameters))
        self.parameters, self.shape = parameters, shape
