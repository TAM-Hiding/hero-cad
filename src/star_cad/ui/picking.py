"""Screen-space polyline hit testing, independent of rendered line width."""
from math import hypot


def candidates(renderer, mesh, x, y, radius):
    result = []
    for cell_id in range(mesh.GetNumberOfCells()):
        cell = mesh.GetCell(cell_id)
        for i in range(cell.GetNumberOfPoints() - 1):
            a, b = (mesh.GetPoint(cell.GetPointId(j)) for j in (i, i+1))
            projected = []
            for point in (a, b):
                renderer.SetWorldPoint(*point, 1)
                renderer.WorldToDisplay()
                projected.append(renderer.GetDisplayPoint())
            p, q = projected
            dx, dy = q[0]-p[0], q[1]-p[1]
            length2 = dx*dx + dy*dy
            t = max(0, min(1, ((x-p[0])*dx+(y-p[1])*dy)/length2)) if length2 else 0
            distance = hypot(x-p[0]-t*dx, y-p[1]-t*dy)
            if distance <= radius:
                point = tuple(a[j]+t*(b[j]-a[j]) for j in range(3))
                result.append((distance, point, cell_id))
    return sorted(result, key=lambda item: item[0])
