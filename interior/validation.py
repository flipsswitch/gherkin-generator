import math
from collections import Counter, defaultdict, deque

from interior.geometry import area, clear_point, corners, in_rect, inside, mesh_health, overlaps, signed_volume


def component_mesh(component, objects):
    obj = objects[component['object']]
    vertices = obj.get('vertices_m', obj.get('vertices'))
    faces = obj['triangles']
    v, f = component['vertex_offset'], component['face_offset']
    return vertices[v:v + component['vertex_count']], [[i - v for i in face] for face in faces[f:f + component['face_count']]]


def triangle_height(x, y, a, b, c):
    det = (b[1] - c[1]) * (a[0] - c[0]) + (c[0] - b[0]) * (a[1] - c[1])
    if abs(det) < 1e-10:
        return None
    u = ((b[1] - c[1]) * (x - c[0]) + (c[0] - b[0]) * (y - c[1])) / det
    v = ((c[1] - a[1]) * (x - c[0]) + (a[0] - c[0]) * (y - c[1])) / det
    if min(u, v, 1 - u - v) < -1e-7:
        return None
    return u * a[2] + v * b[2] + (1 - u - v) * c[2]


def stair_checks(recipe, objects, minimum):
    grid = defaultdict(list)
    for obj in recipe['objects']:
        if obj['category'] not in ('INT_SLABS', 'INT_STAIRS', 'INT_CORE', 'INT_SUPPORTS'):
            continue
        data = objects[obj['name']]
        vertices = data.get('vertices_m', data.get('vertices'))
        for face in data['triangles']:
            a, b, c = [vertices[i] for i in face]
            if abs((b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0])) < 1e-10:
                continue
            xmin, xmax = min(a[0], b[0], c[0]), max(a[0], b[0], c[0])
            ymin, ymax = min(a[1], b[1], c[1]), max(a[1], b[1], c[1])
            if xmax < -3.2 or xmin > 3.2 or ymax < -1.8 or ymin > 1.8:
                continue
            for x in range(math.floor(max(-3.2, xmin)), math.floor(min(3.2, xmax)) + 1):
                for y in range(math.floor(max(-1.8, ymin)), math.floor(min(1.8, ymax)) + 1):
                    grid[(x, y)].append((a, b, c))
    failed, clearances, supported = [], [], 0
    for walk in recipe['stair_walk_points']:
        x, y, z = walk['xyz']
        heights = [h for a, b, c in grid[(math.floor(x), math.floor(y))] if (h := triangle_height(x, y, a, b, c)) is not None]
        foot = any(abs(h - z) <= 0.00002 for h in heights)
        supported += int(foot)
        above = [h - z for h in heights if h - z > 0.03]
        clearance = min(above, default=1000)
        if above:
            clearances.append(clearance)
        if not foot or clearance < minimum - 0.00002:
            failed.append({'component': walk['component'], 'point_m': walk['xyz'], 'foot_supported': foot, 'headroom_m': clearance})
    return {'check': 'stair_treads_and_vertical_headroom', 'pass': not failed,
            'sampled_treads': len(recipe['stair_walk_points']), 'supported_treads': supported,
            'minimum_measured_headroom_m': min(clearances, default=None), 'failures': failed[:30],
            'scope': 'Vertical rays against actual slabs, stair flights, landings, core walls and columns; not a fire or accessibility assessment'}


def segment_distance_3d(p0, p1, q0, q1):
    u = [b - a for a, b in zip(p0, p1)]
    v = [b - a for a, b in zip(q0, q1)]
    w = [a - b for a, b in zip(p0, q0)]
    dot = lambda a, b: sum(x * y for x, y in zip(a, b))
    a, b, c, d, e = dot(u, u), dot(u, v), dot(v, v), dot(u, w), dot(v, w)
    den = a * c - b * b
    s = max(0, min(1, (b * e - c * d) / den)) if den > 1e-12 else 0
    t = (b * s + e) / c
    if t < 0:
        t, s = 0, max(0, min(1, -d / a))
    elif t > 1:
        t, s = 1, max(0, min(1, (b - d) / a))
    return math.sqrt(sum((w[k] + s * u[k] - t * v[k]) ** 2 for k in range(3)))


def pipe_checks(recipe, objects, settings):
    pipes, buckets, clashes = [], defaultdict(list), []
    n = settings['services']['pipe_radial_sides']
    for comp in recipe['components']:
        if comp['role'] != 'service_pipe':
            continue
        vertices, _ = component_mesh(comp, objects)
        a, b = [[sum(p[k] for p in loop) / n for k in range(3)] for loop in (vertices[:n], vertices[n:2 * n])]
        pipes.append({'id': comp['id'], 'system': comp['system'], 'a': a, 'b': b, 'radius': comp['radius_m']})
        low = [math.floor((min(a[k], b[k]) - comp['radius_m']) / 2) for k in range(3)]
        high = [math.floor((max(a[k], b[k]) + comp['radius_m']) / 2) for k in range(3)]
        for x in range(low[0], high[0] + 1):
            for y in range(low[1], high[1] + 1):
                for z in range(low[2], high[2] + 1):
                    buckets[(x, y, z)].append(len(pipes) - 1)
    checked = set()
    for values in buckets.values():
        for pos, i in enumerate(values):
            for j in values[pos + 1:]:
                pair = (min(i, j), max(i, j))
                if pair in checked or pipes[i]['system'] == pipes[j]['system']:
                    continue
                checked.add(pair)
                a, b = pipes[i], pipes[j]
                distance = segment_distance_3d(a['a'], a['b'], b['a'], b['b'])
                if distance < a['radius'] + b['radius'] - 0.00002:
                    clashes.append({'a': a['id'], 'b': b['id'], 'centreline_distance_m': distance})
    graph, terminal_lookup = defaultdict(set), {}
    def key(xyz):
        return tuple(round(v, 4) for v in xyz)
    for pipe in pipes:
        if pipe['system'] == 'FIRE':
            a, b = key(pipe['a']), key(pipe['b'])
            graph[a].add(b)
            graph[b].add(a)
    disconnected = []
    for network in recipe['networks']:
        root = key([4, 0, recipe['floors'][0]['ffl']])
        seen, queue = {root}, deque([root])
        while queue:
            node = queue.popleft()
            for nxt in graph[node]:
                if nxt not in seen:
                    seen.add(nxt)
                    queue.append(nxt)
        for identifier in network['terminals']:
            if not terminal_lookup:
                terminal_lookup = {c['id']: c for c in recipe['components'] if c['role'] == 'sprinkler_head'}
            vertices, _ = component_mesh(terminal_lookup[identifier], objects)
            end = [sum(p[k] for p in vertices[12:24]) / 12 for k in range(3)]
            if key(end) not in seen:
                disconnected.append(identifier)
    return [
        {'check': 'different_pipe_systems_clear', 'pass': not clashes, 'nearby_pairs_tested': len(checked), 'clashes': clashes[:50], 'total_clashes': len(clashes),
         'scope': 'Swept nominal pipe radii; same-system joints excluded; fittings and insulation not represented'},
        {'check': 'sprinkler_terminals_connected_to_main_riser', 'pass': not disconnected, 'terminals': sum(n['routed_terminals'] for n in recipe['networks']), 'disconnected': disconnected[:30]}
    ]


def layout_checks(recipe):
    furniture_clashes, door_clashes = [], []
    for floor in recipe['floors']:
        furniture = floor['furniture']
        for i, a in enumerate(furniture):
            for b in furniture[i + 1:]:
                if overlaps(a['rect'], b['rect']):
                    furniture_clashes.append([a['id'], b['id']])
        enclosures = [(c['id'], c['footprint']) for c in recipe['components'] if c['level'] == floor['level'] and 'footprint' in c]
        for door in (d for d in recipe['doors'] if d['level'] == floor['level']):
            for identifier, rect in enclosures:
                if identifier != door['parent'] and overlaps(door['approach_rect'], rect):
                    door_clashes.append([door['id'], identifier])
    return [
        {'check': 'furniture_clearance_envelopes_disjoint', 'pass': not furniture_clashes, 'clashes': furniture_clashes[:30], 'scope': 'Declared workstation and cafe clearance envelopes'},
        {'check': 'door_approach_envelopes_clear_of_other_enclosures', 'pass': not door_clashes, 'clashes': door_clashes[:30], 'total_clashes': len(door_clashes), 'scope': 'Plan clearance outside doors; closed door leaves are treated as operable'}
    ]


def validate(recipe, settings, readback=None):
    objects = {o.get('name', o.get('id')): o for o in (readback if readback is not None else recipe['objects'])}
    checks = []
    expected_names = {o['name'] for o in recipe['objects']}
    checks.append({'check': 'all_native_objects_present', 'pass': set(objects) == expected_names})
    if set(objects) != expected_names:
        return {'passed': False, 'checks': checks}
    failures, maximum_vertices, maximum_faces = [], 0, 0
    for intended in recipe['objects']:
        obj = objects[intended['name']]
        vertices, faces = obj.get('vertices_m', obj.get('vertices')), obj['triangles']
        maximum_vertices, maximum_faces = max(maximum_vertices, len(vertices)), max(maximum_faces, len(faces))
        if intended['category'].startswith('GHR_GLAZING'):
            continue
        health = mesh_health(vertices, faces)
        if not health['closed_oriented'] or health['degenerate_triangles'] or health['signed_volume_m3'] <= 0:
            failures.append({'id': intended['name'], **health})
    checks.append({'check': 'closed_oriented_positive_solid_meshes', 'pass': not failures, 'failures': failures[:30]})
    checks.append({'check': 'bounded_mesh_objects', 'pass': maximum_vertices <= settings['mesh_limits']['vertices_per_object'] and maximum_faces <= settings['mesh_limits']['triangles_per_object'], 'max_vertices': maximum_vertices, 'max_triangles': maximum_faces})
    for floor in recipe['floors']:
        comp = next(c for c in recipe['components'] if c['level'] == floor['level'] and c['role'] == 'perforated_slab')
        vertices, faces = component_mesh(comp, objects)
        thickness = max(v[2] for v in vertices) - min(v[2] for v in vertices)
        expected_volume = (area(floor['profile']) - sum(r[2] * r[3] for r in floor['openings'])) * thickness
        difference = abs(signed_volume(vertices, faces) - expected_volume)
        blocked = []
        for j, hole in enumerate(floor['openings']):
            for a, b, c in faces:
                if triangle_height(hole[0], hole[1], vertices[a], vertices[b], vertices[c]) is not None:
                    blocked.append(j)
                    break
        checks.append({'check': f'L{floor["level"]:02d}_shaft_openings_and_slab_volume', 'pass': not blocked and difference < 0.005,
                       'volume_difference_m3': difference, 'blocked_opening_centres': blocked})
    checks.append(stair_checks(recipe, objects, settings['validation']['minimum_stair_headroom_m']))
    checks.extend(pipe_checks(recipe, objects, settings))
    checks.extend(layout_checks(recipe))
    return {'passed': all(c['pass'] for c in checks), 'checks': checks,
            'geometry_source': 'reopened native mesh vertices and triangles' if readback is not None else 'generated meshes; native host verification still required',
            'layout_source': 'parameter clearance envelopes, tied to verified component mappings in native reports',
            'omissions': len(recipe['omissions']), 'unverified': recipe['exclusions']}
