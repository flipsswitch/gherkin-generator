import math
from collections import Counter, defaultdict

from gherkin import cross, dot, length, point, sub, triangulate_polygon, unit


def area(poly):
    return sum(a[0] * b[1] - b[0] * a[1] for a, b in zip(poly, poly[1:] + poly[:1])) / 2


def inside(xy, poly):
    x, y = xy
    hit = False
    for a, b in zip(poly, poly[1:] + poly[:1]):
        if (a[1] > y) != (b[1] > y) and x < (b[0] - a[0]) * (y - a[1]) / (b[1] - a[1]) + a[0]:
            hit = not hit
    return hit


def segment_distance(p, a, b):
    dx, dy = b[0] - a[0], b[1] - a[1]
    t = max(0, min(1, ((p[0] - a[0]) * dx + (p[1] - a[1]) * dy) / (dx * dx + dy * dy)))
    return math.hypot(p[0] - a[0] - t * dx, p[1] - a[1] - t * dy)


def clear_point(xy, poly, margin=0):
    if not inside(xy, poly):
        return False
    if margin > 0:
        for a, b in zip(poly, poly[1:] + poly[:1]):
            if min(a[0], b[0]) - margin <= xy[0] <= max(a[0], b[0]) + margin and min(a[1], b[1]) - margin <= xy[1] <= max(a[1], b[1]) + margin:
                if segment_distance(xy, a, b) < margin:
                    return False
    return True


def segment_gap(a, b, c, d):
    def side(p, q, r):
        return (q[0] - p[0]) * (r[1] - p[1]) - (q[1] - p[1]) * (r[0] - p[0])
    if (max(min(a[0], b[0]), min(c[0], d[0])) <= min(max(a[0], b[0]), max(c[0], d[0]))
            and max(min(a[1], b[1]), min(c[1], d[1])) <= min(max(a[1], b[1]), max(c[1], d[1]))
            and side(a, b, c) * side(a, b, d) <= 0 and side(c, d, a) * side(c, d, b) <= 0):
        return 0.0
    return min(segment_distance(a, c, d), segment_distance(b, c, d), segment_distance(c, a, b), segment_distance(d, a, b))


def clear_segment(a, b, poly, margin):
    if not clear_point(a, poly, margin) or not clear_point(b, poly, margin):
        return False
    for c, d in zip(poly, poly[1:] + poly[:1]):
        if (max(a[0], b[0]) + margin < min(c[0], d[0]) or min(a[0], b[0]) - margin > max(c[0], d[0])
                or max(a[1], b[1]) + margin < min(c[1], d[1]) or min(a[1], b[1]) - margin > max(c[1], d[1])):
            continue
        if segment_gap(a, b, c, d) <= margin:
            return False
    return True


def corners(rect, margin=0):
    cx, cy, width, depth, angle = rect
    c, s = math.cos(angle), math.sin(angle)
    return [[cx + x * c - y * s, cy + x * s + y * c]
            for x, y in [(-width / 2 - margin, -depth / 2 - margin),
                         (width / 2 + margin, -depth / 2 - margin),
                         (width / 2 + margin, depth / 2 + margin),
                         (-width / 2 - margin, depth / 2 + margin)]]


def local_xy(rect, x, y):
    cx, cy, _, _, angle = rect
    return [cx + x * math.cos(angle) - y * math.sin(angle), cy + x * math.sin(angle) + y * math.cos(angle)]


def overlaps(a, b, margin=0):
    pa, pb = corners(a, margin), corners(b)
    for angle in (a[4], a[4] + math.pi / 2, b[4], b[4] + math.pi / 2):
        direction = [math.cos(angle), math.sin(angle)]
        va = [sum(x * y for x, y in zip(p, direction)) for p in pa]
        vb = [sum(x * y for x, y in zip(p, direction)) for p in pb]
        if max(va) <= min(vb) + 1e-8 or max(vb) <= min(va) + 1e-8:
            return False
    return True


def in_rect(xy, rect, margin=0):
    cx, cy, w, d, angle = rect
    dx, dy = xy[0] - cx, xy[1] - cy
    return abs(dx * math.cos(angle) + dy * math.sin(angle)) < w / 2 + margin and abs(-dx * math.sin(angle) + dy * math.cos(angle)) < d / 2 + margin


def combine(meshes):
    vertices, faces = [], []
    for v, f in meshes:
        start = len(vertices)
        vertices.extend(v)
        faces.extend([[i + start for i in face] for face in f])
    return vertices, faces


def signed_volume(vertices, faces):
    return sum(dot(vertices[a], cross(vertices[b], vertices[c])) for a, b, c in faces) / 6


def prism(poly, z, height):
    if area(poly) < 0:
        poly = list(reversed(poly))
    cap = triangulate_polygon(poly)
    n = len(poly)
    vertices = [point([x, y, z + dz]) for dz in (0, height) for x, y in poly]
    faces = [[c, b, a] for a, b, c in cap] + [[a + n, b + n, c + n] for a, b, c in cap]
    for j in range(n):
        k = (j + 1) % n
        faces.extend([[j, k, j + n], [k, k + n, j + n]])
    return vertices, faces


def box(rect, z, height):
    return prism(corners(rect), z, height)


def transform(mesh, pose):
    vertices, faces = mesh
    return [[*local_xy([pose[0], pose[1], 0, 0, pose[2]], x, y), z] for x, y, z in vertices], faces


def section_member(a, b, width, depth, web=0.012, flange=0.018):
    dx, dy = b[0] - a[0], b[1] - a[1]
    span = math.hypot(dx, dy)
    rect = [(a[0] + b[0]) / 2, (a[1] + b[1]) / 2, span, width, math.atan2(dy, dx)]
    return combine([box(rect, a[2] - depth / 2, flange), box(rect, a[2] + depth / 2 - flange, flange),
                    box([rect[0], rect[1], span, web, rect[4]], a[2] - depth / 2 + flange, depth - 2 * flange)])


def tube(a, b, radius, sides=8):
    axis = unit(sub(b, a))
    ref = [0, 0, 1] if abs(axis[2]) < 0.9 else [0, 1, 0]
    u = unit(cross(ref, axis))
    v = cross(axis, u)
    vertices = [point([p[k] + radius * (u[k] * math.cos(2 * math.pi * j / sides) + v[k] * math.sin(2 * math.pi * j / sides)) for k in range(3)])
                for p in (a, b) for j in range(sides)]
    faces = [[0, j + 1, j] for j in range(1, sides - 1)] + [[sides, sides + j, sides + j + 1] for j in range(1, sides - 1)]
    for j in range(sides):
        k = (j + 1) % sides
        faces.extend([[j, k, j + sides], [k, k + sides, j + sides]])
    return vertices, faces


def stair_flight(x0, x1, y0, direction, z, risers, rise, going, waist):
    profile = [[0, 0]]
    for i in range(risers):
        profile.extend([[i * going, (i + 1) * rise], [(i + 1) * going, (i + 1) * rise]])
    profile.extend([[risers * going, (risers - 1) * rise - waist], [0, -waist]])
    vertices, faces = prism(profile, 0, x1 - x0)
    vertices = [point([x0 + w, y0 + direction * u, z + v]) for u, v, w in vertices]
    if signed_volume(vertices, faces) < 0:
        faces = [[c, b, a] for a, b, c in faces]
    return vertices, faces


def perforated_slab(poly, holes, z, thickness, opening_polygons=None):
    for hole in holes:
        if not all(clear_point(p, poly, 1e-5) for p in corners(hole)):
            raise ValueError(f'Shaft opening {hole} lies outside its slab at {z} m')
    for i, a in enumerate(holes):
        for b in holes[i + 1:]:
            if overlaps(a, b):
                raise ValueError(f'Slab openings must be disjoint rectangles: {a}, {b}')
    opening_polygons = opening_polygons or []
    for opening in opening_polygons:
        if len(opening) < 3 or not all(clear_point(p, poly, 1e-5) for p in opening):
            raise ValueError('Polygonal opening lies outside its slab')
        if any(any(in_rect(p, rect) for p in opening) or any(inside(p, opening) for p in corners(rect)) for rect in holes):
            raise ValueError('Polygonal and rectangular openings overlap')
    loops = [[[round(v, 6) for v in xy] for xy in loop] for loop in [poly] + [corners(hole) for hole in holes] + opening_polygons]
    xs = sorted({x for loop in loops for x, _ in loop})
    cells = []
    for xl, xr in zip(xs, xs[1:]):
        if xr - xl < 1e-8:
            continue
        xm = (xl + xr) / 2
        crossing = []
        for loop in loops:
            for a, b in zip(loop, loop[1:] + loop[:1]):
                if min(a[0], b[0]) < xm < max(a[0], b[0]):
                    yy = lambda x: a[1] + (x - a[0]) * (b[1] - a[1]) / (b[0] - a[0])
                    crossing.append((yy(xm), yy(xl), yy(xr)))
        crossing.sort()
        if len(crossing) % 2:
            raise ValueError('Invalid slab scanline')
        for lower, upper in zip(crossing[::2], crossing[1::2]):
            cells.append([[xl, lower[1]], [xr, lower[2]], [xr, upper[2]], [xl, upper[1]]])
    cuts_by_x = defaultdict(set)
    for cell in cells:
        for x, y in cell:
            cuts_by_x[round(x, 6)].add(round(y, 6))
    vertices, faces, indices = [], [], {}

    def vertex(p):
        key = tuple(round(v, 6) for v in p)
        if key not in indices:
            indices[key] = len(vertices)
            vertices.append(list(key))
        return indices[key]

    for cell in cells:
        boundary = []
        for a, b in zip(cell, cell[1:] + cell[:1]):
            boundary.append(a)
            if abs(a[0] - b[0]) < 1e-8:
                ys = sorted(y for y in cuts_by_x[round(a[0], 6)] if min(a[1], b[1]) + 1e-6 < y < max(a[1], b[1]) - 1e-6)
                boundary.extend([[a[0], y] for y in (ys if b[1] > a[1] else reversed(ys))])
        boundary = [p for i, p in enumerate(boundary) if math.dist(p, boundary[i - 1]) > 1e-7]
        if len(boundary) < 3 or area(boundary) < 1e-10:
            continue
        center = [sum(p[k] for p in boundary) / len(boundary) for k in (0, 1)]
        ci = vertex(center)
        loop = [vertex(p) for p in boundary]
        for a, b in zip(loop, loop[1:] + loop[:1]):
            if a != b:
                faces.append([ci, a, b])
    boundary_edges = Counter((a, b) for face in faces for a, b in zip(face, face[1:] + face[:1]))
    boundary = [(a, b) for a, b in boundary_edges if (b, a) not in boundary_edges]
    n = len(vertices)
    result_vertices = [[x, y, z + dz] for dz in (0, thickness) for x, y in vertices]
    result_faces = [[c, b, a] for a, b, c in faces] + [[a + n, b + n, c + n] for a, b, c in faces]
    for a, b in boundary:
        result_faces.extend([[a, b, a + n], [b, b + n, a + n]])
    return result_vertices, result_faces


def mesh_health(vertices, faces):
    edges = Counter((a, b) for f in faces for a, b in zip(f, f[1:] + f[:1]))
    degenerate = sum(length(cross(sub(vertices[b], vertices[a]), sub(vertices[c], vertices[a]))) <= 1e-12 for a, b, c in faces)
    return {'closed_oriented': all(count == 1 and edges[(b, a)] == 1 for (a, b), count in edges.items()),
            'degenerate_triangles': degenerate, 'signed_volume_m3': signed_volume(vertices, faces)}
