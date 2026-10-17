import argparse
import hashlib
import json
import math
from pathlib import Path


ROOT = Path(__file__).resolve().parent


def rounded(value):
    return 0.0 if abs(value) < 5e-10 else round(value, 9)


def point(values):
    return [rounded(value) for value in values]


def add(a, b):
    return [x + y for x, y in zip(a, b)]


def sub(a, b):
    return [x - y for x, y in zip(a, b)]


def scale(a, factor):
    return [x * factor for x in a]


def dot(a, b):
    return sum(x * y for x, y in zip(a, b))


def cross(a, b):
    return [a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0]]


def length(a):
    return math.sqrt(dot(a, a))


def unit(a):
    return scale(a, 1 / length(a))


def radius_function(knots):
    z = [v[0] for v in knots]
    q = [v[1] ** 2 for v in knots]
    h = [b - a for a, b in zip(z, z[1:])]
    d = [(q[i + 1] - q[i]) / h[i] for i in range(len(h))]
    m = [0.0] * len(z)

    def endpoint(h0, h1, d0, d1):
        value = ((2 * h0 + h1) * d0 - h0 * d1) / (h0 + h1)
        if value * d0 <= 0:
            return 0.0
        if d0 * d1 < 0 and abs(value) > 3 * abs(d0):
            return 3 * d0
        return value

    m[0] = endpoint(h[0], h[1], d[0], d[1])
    m[-1] = endpoint(h[-1], h[-2], d[-1], d[-2])
    for i in range(1, len(z) - 1):
        if d[i - 1] * d[i] > 0:
            w1, w2 = 2 * h[i] + h[i - 1], h[i] + 2 * h[i - 1]
            m[i] = (w1 + w2) / (w1 / d[i - 1] + w2 / d[i])

    def radius(value):
        if not math.isfinite(value) or value < z[0] or value > z[-1]:
            raise ValueError('Elevation outside the radius profile')
        i = 0
        while i < len(z) - 2 and value > z[i + 1]:
            i += 1
        t = (value - z[i]) / h[i]
        squared = ((2 * t ** 3 - 3 * t ** 2 + 1) * q[i]
                   + (t ** 3 - 2 * t ** 2 + t) * h[i] * m[i]
                   + (-2 * t ** 3 + 3 * t ** 2) * q[i + 1]
                   + (t ** 3 - t ** 2) * h[i] * m[i + 1])
        return math.sqrt(max(0.0, squared))

    return radius


def load_parameters(filename=None):
    with Path(filename or ROOT / 'parameters.json').open(encoding='utf-8-sig') as stream:
        parameters = json.load(stream)
    validate_parameters(parameters)
    return parameters


def validate_parameters(p):
    def finite(value):
        if isinstance(value, dict):
            return all(finite(v) for v in value.values())
        if isinstance(value, list):
            return all(finite(v) for v in value)
        return not isinstance(value, (int, float)) or math.isfinite(value)

    if not finite(p):
        raise ValueError('Parameters must contain finite numbers')
    if p['units'] != 'metres' or p['axis'] != 'Z-up' or p['origin_m'] != [0, 0, 0]:
        raise ValueError('This recipe uses metres, Z-up and the zero origin')
    knots = p['profile_knots_z_radius_m']
    if len(knots) < 3 or any(b[0] <= a[0] for a, b in zip(knots, knots[1:])):
        raise ValueError('Profile elevations must strictly increase')
    if any(r < 0 for _, r in knots) or knots[0][0] != 0 or knots[-1] != [p['height_m'], 0]:
        raise ValueError('Profile must start at zero elevation and end at the apex')
    floors = p['floor_elevations_m']
    if not floors or len(floors) != p['floor_count'] or len(floors) > 120 or floors != sorted(set(floors)):
        raise ValueError('Floor schedule must be ordered, unique and match floor_count')
    for key in ('regular_height_module_m', 'slab_thickness_m', 'diagrid_ring_step_m', 'diagrid_member_radius_m', 'glazing_regular_ring_step_m'):
        if p[key] <= 0:
            raise ValueError(key + ' must be positive')
    for key, low, high in (('atrium_count', 1, 24), ('diagrid_nodes_per_ring', 3, 128), ('glazing_samples_per_ring', 3, 256), ('diagrid_tube_radial_sides', 3, 32)):
        if not isinstance(p[key], int) or not low <= p[key] <= high:
            raise ValueError(key + ' is outside the supported integer range')
    if not 0 < p['atrium_angular_width_deg'] < 360 / p['atrium_count']:
        raise ValueError('Atrium notches must leave positive outer arcs')
    if not 0 < p['atrium_inner_radius_fraction_of_floor_radius'] < 1:
        raise ValueError('Atrium inner radius fraction must be between zero and one')
    if not all(0 <= p[key] <= 1 for key in ('glazing_clear_opacity', 'glazing_dark_opacity')):
        raise ValueError('Opacity must be between zero and one')
    radius = radius_function(knots)
    if any(z < 0 or z + p['slab_thickness_m'] > p['height_m'] or radius(z) <= p['floor_radial_inset_m'] for z in floors):
        raise ValueError('Floor lies outside the usable profile')
    for step in ('diagrid_ring_step_m', 'glazing_regular_ring_step_m'):
        bays = p['diagrid_body_top_m'] / p[step]
        if abs(bays - round(bays)) > 1e-8 or bays > 500:
            raise ValueError('Body height must contain a bounded integral number of bays')
    crown = p['glazing_crown_ring_elevations_m']
    if crown != sorted(set(crown)) or not crown or crown[0] <= p['diagrid_body_top_m'] or crown[-1] >= p['height_m']:
        raise ValueError('Crown rings must increase between the body and apex')
    if p['glazing_crown_apex_z_m'] != p['height_m']:
        raise ValueError('Crown apex must match the height')


def generate(p):
    validate_parameters(p)
    radius = radius_function(p['profile_knots_z_radius_m'])
    phase = lambda z: p['rotation_deg_per_regular_height_module'] * z / p['regular_height_module_m']

    def ring_point(z, angle, inset=0):
        angle = math.radians(angle)
        return point([(radius(z) - inset) * math.cos(angle), (radius(z) - inset) * math.sin(angle), z])

    objects, floors, nodes, members, faces, vertices = [], [], [], [], [], []
    for i, z in enumerate(p['floor_elevations_m']):
        r = radius(z) - p['floor_radial_inset_m']
        full = round(z / p['regular_height_module_m']) % 6 == 0
        name = f'GHR-FLOOR-{i + 1:02d}'
        profile = []
        if not full:
            half = p['atrium_angular_width_deg'] / 2
            sector = 360 / p['atrium_count']
            inner = r * p['atrium_inner_radius_fraction_of_floor_radius']

            def polar(radial, angle):
                return point([radial * math.cos(math.radians(angle)), radial * math.sin(math.radians(angle))])

            for a in range(p['atrium_count']):
                center = phase(z) + a * sector
                profile.append(polar(r, center - half))
                count = math.ceil(2 * half / 4)
                profile.extend(polar(inner, center - half + 2 * half * j / count) for j in range(count + 1))
                profile.append(polar(r, center + half))
                count = math.ceil((sector - 2 * half) / 4)
                profile.extend(polar(r, center + half + (sector - 2 * half) * j / count) for j in range(1, count))
        obj = {'name': name, 'category': 'GHR_FLOORS', 'color': 8, 'opacity': 1.0,
               'kind': 'cylinder' if full else 'extrude', 'elevation': z, 'radius': rounded(r),
               'thickness': p['slab_thickness_m'], 'profile': profile}
        objects.append(obj)
        floors.append({'id': name, 'elevation': z, 'radius': r, 'notched': not full, 'phase_degrees': phase(z)})

    count = p['diagrid_nodes_per_ring']
    bays = round(p['diagrid_body_top_m'] / p['diagrid_ring_step_m'])
    for k in range(bays + 1):
        for j in range(count):
            nodes.append({'id': f'N-{k:02d}-{j:02d}', 'ring': k, 'index': j,
                          'xyz': ring_point(k * p['diagrid_ring_step_m'], 360 * j / count + p['diagrid_ring_rotation_step_deg'] * k, p['diagrid_radial_inset_m'])})
    for k in range(bays):
        for j in range(count):
            for family in ('A', 'B'):
                target = j if family == 'A' else (j - 1) % count
                a, b = nodes[k * count + j], nodes[(k + 1) * count + target]
                members.append({'id': f'GHR-MEMBER-{family}-{k:02d}-{j:02d}', 'family': family,
                                'start_node': a['id'], 'end_node': b['id'], 'start': a['xyz'], 'end': b['xyz']})
    sides = p['diagrid_tube_radial_sides']
    for start in range(0, len(members), 16):
        name = f'GHR-DIAGRID-{start // 16:03d}'
        mesh_vertices, triangles = [], []
        for member in members[start:start + 16]:
            offset, face_offset = len(mesh_vertices), len(triangles)
            w = unit(sub(member['end'], member['start']))
            u = unit(cross(w, [0, 0, 1] if abs(w[2]) < .99 else [0, 1, 0]))
            v = cross(w, u)
            for end in (member['start'], member['end']):
                for j in range(sides):
                    angle = 2 * math.pi * j / sides
                    mesh_vertices.append(point(add(end, add(scale(u, p['diagrid_member_radius_m'] * math.cos(angle)), scale(v, p['diagrid_member_radius_m'] * math.sin(angle))))))
            for j in range(sides):
                t = (j + 1) % sides
                triangles.extend([[offset + j, offset + t, offset + sides + j], [offset + t, offset + sides + t, offset + sides + j]])
            for j in range(1, sides - 1):
                triangles.extend([[offset, offset + j + 1, offset + j], [offset + sides, offset + sides + j, offset + sides + j + 1]])
            member.update(object=name, vertex_offset=offset, vertex_count=2 * sides, face_offset=face_offset, face_count=len(triangles) - face_offset)
        objects.append({'name': name, 'category': 'GHR_DIAGRID', 'kind': 'mesh', 'color': 8, 'opacity': 1.0, 'vertices': mesh_vertices, 'triangles': triangles})

    regular = round(p['diagrid_body_top_m'] / p['glazing_regular_ring_step_m'])
    zs = [rounded(i * p['glazing_regular_ring_step_m']) for i in range(regular + 1)] + p['glazing_crown_ring_elevations_m']
    count = p['glazing_samples_per_ring']
    for k, z in enumerate(zs):
        vertices.extend(ring_point(z, 360 * j / count + phase(z)) for j in range(count))
    apex = len(vertices)
    vertices.append([0.0, 0.0, p['height_m']])

    def face(indices, strip):
        a, b, c = [vertices[i] for i in indices]
        centroid = scale(add(add(a, b), c), 1 / 3)
        if dot(cross(sub(b, a), sub(c, a)), [centroid[0], centroid[1], 0]) <= 0:
            raise ValueError('Facade triangle points inward')
        azimuth = math.degrees(math.atan2(centroid[1], centroid[0]))
        period = 360 / p['atrium_count']
        delta = (azimuth - phase(centroid[2]) + period / 2) % period - period / 2
        appearance = 'dark' if abs(delta) <= p['atrium_angular_width_deg'] / 2 else 'clear'
        faces.append({'id': f'GHR-FACE-{len(faces):05d}', 'vertices': indices, 'strip': strip, 'appearance': appearance})

    for k in range(len(zs) - 1):
        for j in range(count):
            t = (j + 1) % count
            face([k * count + j, k * count + t, (k + 1) * count + j], k)
            face([k * count + t, (k + 1) * count + t, (k + 1) * count + j], k)
    for j in range(count):
        face([(len(zs) - 1) * count + j, (len(zs) - 1) * count + (j + 1) % count, apex], len(zs) - 1)
    for band in range(0, len(zs), 4):
        for appearance in ('clear', 'dark'):
            selected = [f for f in faces if band <= f['strip'] < band + 4 and f['appearance'] == appearance]
            if not selected:
                continue
            vertex_ids = sorted({i for f in selected for i in f['vertices']})
            local = {value: i for i, value in enumerate(vertex_ids)}
            objects.append({'name': f'GHR-GLASS-{appearance.upper()}-{band // 4:02d}',
                            'category': f'GHR_GLAZING_{appearance.upper()}', 'kind': 'mesh',
                            'color': 7 if appearance == 'clear' else 1, 'opacity': p[f'glazing_{appearance}_opacity'],
                            'vertices': [vertices[i] for i in vertex_ids],
                            'triangles': [[local[i] for i in f['vertices']] for f in selected],
                            'logical_vertex_ids': vertex_ids, 'logical_face_ids': [f['id'] for f in selected]})
    result = {'units': 'metres', 'axis': 'Z-up', 'objects': objects, 'floors': floors, 'nodes': nodes,
              'members': members, 'facade': {'vertices': vertices, 'faces': faces},
              'representation': 'Approximate architectural reconstruction; not as-built or structural'}
    result['counts'] = {'floors': len(floors), 'nodes': len(nodes), 'members': len(members),
                        'facade_vertices': len(vertices), 'facade_faces': len(faces), 'objects': len(objects)}
    return result


def triangulate_polygon(profile):
    area = sum(a[0] * b[1] - a[1] * b[0] for a, b in zip(profile, profile[1:] + profile[:1]))
    if area <= 0:
        raise ValueError('Floor profile must have positive winding')
    remaining, triangles = list(range(len(profile))), []

    def turn(a, b, c):
        return (b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0])

    while len(remaining) > 3:
        for pos, b in enumerate(remaining):
            a, c = remaining[pos - 1], remaining[(pos + 1) % len(remaining)]
            pa, pb, pc = profile[a], profile[b], profile[c]
            if turn(pa, pb, pc) <= 1e-10:
                continue
            if any(turn(pa, pb, profile[i]) >= -1e-10 and turn(pb, pc, profile[i]) >= -1e-10 and turn(pc, pa, profile[i]) >= -1e-10 for i in remaining if i not in (a, b, c)):
                continue
            triangles.append([a, b, c])
            remaining.pop(pos)
            break
        else:
            raise ValueError('Could not triangulate the concave floor without degenerate faces')
    triangles.append(remaining)
    return triangles


def mesh_for_object(obj, circle_sides=512):
    if obj['kind'] == 'mesh':
        return obj['vertices'], obj['triangles']
    if circle_sides < 32:
        raise ValueError('Circular floor sampling requires at least 32 sides')
    if obj['kind'] == 'cylinder':
        profile = [[obj['radius'] * math.cos(2 * math.pi * j / circle_sides), obj['radius'] * math.sin(2 * math.pi * j / circle_sides)] for j in range(circle_sides)]
        cap = [[0, j, j + 1] for j in range(1, circle_sides - 1)]
    else:
        profile = obj['profile']
        cap = triangulate_polygon(profile)
    n = len(profile)
    vertices = [[x, y, obj['elevation'] + dz] for dz in (0, obj['thickness']) for x, y in profile]
    triangles = [[c, b, a] for a, b, c in cap] + [[a + n, b + n, c + n] for a, b, c in cap]
    for j in range(n):
        t = (j + 1) % n
        triangles.extend([[j, t, n + j], [t, n + t, n + j]])
    return vertices, triangles


def geometry_digest(vertices, triangles):
    payload = {'vertices': [[round(v * 1_000_000) for v in xyz] for xyz in vertices], 'triangles': triangles}
    return hashlib.sha256(json.dumps(payload, separators=(',', ':'), sort_keys=True).encode()).hexdigest()


def write_json(filename, data):
    Path(filename).write_text(json.dumps(data, indent=2, allow_nan=False) + '\n', encoding='utf-8')


def main():
    parser = argparse.ArgumentParser(description='Generate the approximate Gherkin geometry without CAD or an MCP server.')
    parser.add_argument('--parameters', type=Path, default=ROOT / 'parameters.json')
    parser.add_argument('--output', type=Path, default=Path('gherkin-geometry.json'))
    args = parser.parse_args()
    if args.output.exists():
        parser.error('Output exists; choose a new filename')
    result = generate(load_parameters(args.parameters))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    write_json(args.output, result)
    print(json.dumps(result['counts']))


if __name__ == '__main__':
    main()
