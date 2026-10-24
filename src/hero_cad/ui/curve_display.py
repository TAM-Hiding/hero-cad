"""Screen-error-bounded display sampling; never used to build CAD geometry."""
from math import asin, ceil, cos, log2, pi, radians, sin, sqrt
from hero_cad.sketch import Circle, Slot

PIXEL_ERROR = 0.25
MAX_SEGMENTS = 32768


def segment_count(entity, pixels_per_mm):
    """Full-circle count in power-of-two quality bands.

    Orthographic projection cannot stretch an orthonormal sketch frame more
    than pixels_per_mm. This conservative bound is independent of view angle,
    so pan/orbit do not invalidate tessellation. A safety cap bounds work for
    enormous mostly-offscreen curves under extreme magnification.
    """
    if not isinstance(entity, (Circle, Slot)):
        return 0
    radius_pixels = entity.radius*pixels_per_mm
    # Stable sagitta relation: error/r = 2 sin(step/4)^2.
    step = 4*asin(sqrt(min(PIXEL_ERROR/(2*radius_pixels), .5)))
    required = max(32, ceil(2*pi/step))
    return min(MAX_SEGMENTS, 2**ceil(log2(required)))


def display_points(entity, count):
    if not count:
        return entity.points
    def arc(center, start, sweep, segments):
        return tuple((center[0]+entity.radius*cos(start+sweep*i/segments),
                      center[1]+entity.radius*sin(start+sweep*i/segments))
                     for i in range(segments+1))
    if isinstance(entity, Circle):
        points = arc((entity.x, entity.y), 0, 2*pi, count)
        return points[:-1] + (points[0],)
    angle = radians(entity.angle)
    right = arc(entity.second_center, angle-pi/2, pi, count//2)
    left = arc((entity.x, entity.y), angle+pi/2, pi, count//2)
    return (left[-1],) + right + left[:-1] + (left[-1],)
