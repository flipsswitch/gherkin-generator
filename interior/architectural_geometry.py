import math

from gherkin import cross, dot, point, sub, unit
from interior.geometry import prism


def basis(a, b):
    axis = unit(sub(b, a))
    reference = [0, 0, 1] if abs(axis[2]) < 0.9 else [0, 1, 0]
    u = unit(cross(reference, axis))
    return u, cross(axis, u), axis


def profile_member(a, b, profile):
    u, v, axis = basis(a, b)
    vertices, faces = prism(profile, 0, math.dist(a, b))
    return [point([a[k] + x * u[k] + y * v[k] + z * axis[k] for k in range(3)]) for x, y, z in vertices], faces


def triangular_member(a, b, width, depth):
    return profile_member(a, b, [[-width / 2, -depth / 3], [width / 2, -depth / 3], [0, depth * 2 / 3]])


def rectangular_member(a, b, width, depth):
    return profile_member(a, b, [[-width / 2, -depth / 2], [width / 2, -depth / 2], [width / 2, depth / 2], [-width / 2, depth / 2]])


def vertical_panel(profile_xz, y, thickness):
    vertices, faces = prism(profile_xz, -thickness / 2, thickness)
    return [[x, y + depth, z] for x, z, depth in vertices], [[c, b, a] for a, b, c in faces]


def hollow_member(a, b, radius_a, radius_b, wall_a, wall_b, sides=24):
    if not 0 < wall_a < radius_a or not 0 < wall_b < radius_b or sides < 6:
        raise ValueError('Invalid hollow member section')
    u, v, _ = basis(a, b)
    rings = [(a, radius_a), (b, radius_b), (a, radius_a - wall_a), (b, radius_b - wall_b)]
    vertices = [point([p[k] + radius * (u[k] * math.cos(math.tau * j / sides) + v[k] * math.sin(math.tau * j / sides)) for k in range(3)])
                for p, radius in rings for j in range(sides)]
    faces = []
    def quad(a, b, c, d):
        faces.extend([[a, b, c], [a, c, d]])
    for j in range(sides):
        k = (j + 1) % sides
        quad(j, k, sides + k, sides + j)
        quad(2 * sides + k, 2 * sides + j, 3 * sides + j, 3 * sides + k)
        quad(k, j, 2 * sides + j, 2 * sides + k)
        quad(sides + j, sides + k, 3 * sides + k, 3 * sides + j)
    return vertices, faces


def ring(cx, cy, z, outer, inner, height, sides=64):
    return hollow_member([cx, cy, z], [cx, cy, z + height], outer, outer, outer - inner, outer - inner, sides)


def ellipsoid(center, radii, sides=12, rows=6):
    vertices = [[center[0], center[1], center[2] - radii[2]]]
    for i in range(1, rows):
        phi = -math.pi / 2 + math.pi * i / rows
        vertices.extend([point([center[0] + radii[0] * math.cos(phi) * math.cos(math.tau * j / sides),
                                center[1] + radii[1] * math.cos(phi) * math.sin(math.tau * j / sides),
                                center[2] + radii[2] * math.sin(phi)]) for j in range(sides)])
    top = len(vertices)
    vertices.append([center[0], center[1], center[2] + radii[2]])
    faces = [[0, 1 + (j + 1) % sides, 1 + j] for j in range(sides)]
    for i in range(rows - 2):
        a, b = 1 + i * sides, 1 + (i + 1) * sides
        for j in range(sides):
            k = (j + 1) % sides
            faces.extend([[a + j, a + k, b + j], [a + k, b + k, b + j]])
    faces.extend([[top - sides + j, top - sides + (j + 1) % sides, top] for j in range(sides)])
    return vertices, faces


def split_polygon(poly, distance, tolerance=1e-9):
    positive, negative = [], []
    for a, b in zip(poly, poly[1:] + poly[:1]):
        da, db = distance(a), distance(b)
        if da >= -tolerance:
            positive.append(a)
        if da <= tolerance:
            negative.append(a)
        if da * db < 0 and abs(da) > tolerance and abs(db) > tolerance:
            p = [a[k] + da / (da - db) * (b[k] - a[k]) for k in range(3)]
            positive.append(p)
            negative.append(p)
    return positive, negative


def subtract_portal(poly, profile_xz, front_y):
    pending, outside = [poly], []
    distances = [lambda p: front_y - p[1]]
    for a, b in zip(profile_xz, profile_xz[1:] + profile_xz[:1]):
        distances.append(lambda p, a=a, b=b: (b[0] - a[0]) * (p[2] - a[1]) - (b[1] - a[1]) * (p[0] - a[0]))
    for distance in distances:
        remaining = []
        for polygon in pending:
            inside, external = split_polygon(polygon, distance)
            if len(external) >= 3:
                outside.append(external)
            if len(inside) >= 3:
                remaining.append(inside)
        pending = remaining
    return outside


def triangle_fan(poly):
    clean = []
    for p in poly:
        if not clean or math.dist(p, clean[-1]) > 1e-7:
            clean.append(point(p))
    if len(clean) > 1 and math.dist(clean[0], clean[-1]) < 1e-7:
        clean.pop()
    triangles = []
    for j in range(1, len(clean) - 1):
        normal = cross(sub(clean[j], clean[0]), sub(clean[j + 1], clean[0]))
        if dot(normal, normal) > 1e-14:
            triangles.append([0, j, j + 1])
    return clean, triangles
