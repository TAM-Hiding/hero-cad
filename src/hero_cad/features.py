"""Ordered immutable feature definitions; no UI or display references."""
from dataclasses import dataclass, field
from math import isfinite
from hero_cad.sketch import SketchParameters, new_id, valid_id


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
    operation: str = 'new'
    target_id: str | None = None
    extent: str = 'distance'
    direction: int = 1
    line_ids: tuple = ()

    def __post_init__(self):
        if self.operation not in ('new', 'join', 'cut', 'intersect'):
            raise ValueError('Unsupported extrusion operation')
        if self.operation == 'new':
            if self.target_id is not None:
                raise ValueError('New Body must not reference a target')
        else:
            valid_id(self.target_id)
        if self.extent not in ('distance', 'through_all') or (self.extent == 'through_all' and self.operation != 'cut'):
            raise ValueError('Through All is supported only for Cut')
        if type(self.direction) is not int or self.direction not in (-1, 1):
            raise ValueError('Direction must be +1 or -1')
        if self.extent == 'distance':
            # Signed distance already encodes direction; keep the legacy form canonical.
            object.__setattr__(self, 'direction', 1)
        valid_id(self.sketch_id)
        valid_id(self.outer_id)
        if not isinstance(self.line_ids, tuple) or len(self.line_ids) > 256:
            raise ValueError('Invalid line-profile membership')
        for identifier in self.line_ids:
            valid_id(identifier)
        if self.line_ids != tuple(sorted(set(self.line_ids))):
            raise ValueError('Line-profile membership must be unique and sorted')
        if not isinstance(self.hole_ids, tuple) or len(self.hole_ids) > 255:
            raise ValueError('Invalid profile holes')
        for identifier in self.hole_ids:
            valid_id(identifier)
        if len(set(self.hole_ids)) != len(self.hole_ids) or self.outer_id in self.hole_ids:
            raise ValueError('Profile boundaries must be distinct')
        if type(self.distance) not in (int, float) or not isfinite(self.distance) or not 1e-6 <= abs(self.distance) <= 100000:
            raise ValueError('Extrusion distance must be finite and nonzero, from ±0.000001 to ±100000 mm')


@dataclass(frozen=True)
class BooleanParameters:
    operation: str
    target_id: str
    tool_ids: tuple

    def __post_init__(self):
        if self.operation not in ('join', 'cut', 'intersect'):
            raise ValueError('Unsupported Boolean operation')
        valid_id(self.target_id)
        if not isinstance(self.tool_ids, tuple) or not 1 <= len(self.tool_ids) <= 31:
            raise ValueError('Combine requires 1–31 tool bodies')
        for identifier in self.tool_ids:
            valid_id(identifier)
        if len(set((self.target_id, *self.tool_ids))) != len(self.tool_ids)+1:
            raise ValueError('Boolean target and tools must be distinct')


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
        expected = {'box': BoxParameters, 'sketch': SketchParameters, 'extrude': ExtrudeParameters, 'boolean': BooleanParameters}.get(self.type)
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
