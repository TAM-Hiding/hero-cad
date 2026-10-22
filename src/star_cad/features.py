"""Ordered immutable feature definitions; no UI or display references."""
from dataclasses import dataclass, field
from math import isfinite
from star_cad.sketch import SketchParameters, new_id, valid_id


@dataclass(frozen=True)
class BoxParameters:
    width: float = 40.0
    depth: float = 30.0
    height: float = 20.0

    def __post_init__(self):
        for value in (self.width, self.depth, self.height):
            if type(value) not in (int, float) or not isfinite(value) or not 0.001 <= value <= 100000:
                raise ValueError('Dimensions must be finite numbers between 0.001 and 100000 mm')


@dataclass(frozen=True)
class ExtrudeParameters:
    sketch_id: str
    outer_id: str
    hole_ids: tuple = ()
    distance: float = 10.0

    def __post_init__(self):
        valid_id(self.sketch_id)
        valid_id(self.outer_id)
        if not isinstance(self.hole_ids, tuple) or len(self.hole_ids) > 255:
            raise ValueError('Invalid profile holes')
        for identifier in self.hole_ids:
            valid_id(identifier)
        if len(set(self.hole_ids)) != len(self.hole_ids) or self.outer_id in self.hole_ids:
            raise ValueError('Profile boundaries must be distinct')
        if type(self.distance) not in (int, float) or not isfinite(self.distance) or not 1e-6 <= abs(self.distance) <= 100000:
            raise ValueError('Extrusion distance must be finite and nonzero, from ±0.000001 to ±100000 mm')


@dataclass(frozen=True)
class Feature:
    type: str
    parameters: object
    references: tuple = ()
    id: str = field(default_factory=new_id)

    def __post_init__(self):
        valid_id(self.id)
        if not isinstance(self.type, str):
            raise ValueError('Feature type must be a string')
        expected = {'box': BoxParameters, 'sketch': SketchParameters, 'extrude': ExtrudeParameters}.get(self.type)
        if expected is None or type(self.parameters) is not expected:
            raise ValueError('Unsupported feature or parameter type')
        if not isinstance(self.references, tuple) or any(not isinstance(r, str) for r in self.references):
            raise ValueError('Feature references must be an immutable sequence of IDs')
        if len(set(self.references)) != len(self.references):
            raise ValueError('Duplicate feature references')


@dataclass(frozen=True)
class FeatureStatus:
    valid: bool
    error: str | None = None


class FeatureError(ValueError):
    def __init__(self, feature_id, message):
        self.feature_id = feature_id
        self.status = FeatureStatus(False, str(message))
        super().__init__(f'Feature {feature_id}: {message}')
