import math

from gherkin import cross, dot, sub
from interior.architectural_geometry import basis
from interior.validation import component_mesh


def segment_triangle(a, b, triangle):
    direction = sub(b, a)
    v0, v1, v2 = triangle
    e1, e2 = sub(v1, v0), sub(v2, v0)
    h = cross(direction, e2)
    det = dot(e1, h)
    if abs(det) < 1e-10:
        return False
    s = sub(a, v0)
    u = dot(s, h) / det
    q = cross(s, e1)
    v = dot(direction, q) / det
    t = dot(e2, q) / det
    return -1e-7 <= u <= 1 + 1e-7 and -1e-7 <= v and u + v <= 1 + 1e-7 and 0 <= t <= 1


def architectural_checks(recipe, settings, objects):
    failures, max_section_error = [], 0
    hollow_count, crown_count, lobby_count = 0, 0, 0
    doors = []
    for comp in recipe['components']:
        role = comp['role']
        if role not in ('crown_triangular_member', 'hollow_diagrid_member', 'revolving_door_header', 'lobby_aluminium_panel'):
            continue
        vertices, faces = component_mesh(comp, objects)
        if role == 'crown_triangular_member':
            crown_count += 1
            u, v, _ = basis(comp['start_m'], comp['end_m'])
            measures = [max(dot(sub(p, comp['start_m']), axis) for p in vertices[:3]) - min(dot(sub(p, comp['start_m']), axis) for p in vertices[:3]) for axis in (u, v)]
            error = max(abs(a - b) for a, b in zip(measures, [0.11, 0.15]))
            max_section_error = max(max_section_error, error)
            if error > 0.00003:
                failures.append(comp['id'])
        elif role == 'hollow_diagrid_member':
            hollow_count += 1
            n = comp['ring_vertices']
            for end, outer_offset, inner_offset in ((0, 0, 2 * n), (1, n, 3 * n)):
                outer = vertices[outer_offset:outer_offset + n]
                inner = vertices[inner_offset:inner_offset + n]
                center = [sum(p[k] for p in outer) / n for k in range(3)]
                radius = sum(math.dist(p, center) for p in outer) / n
                inner_radius = sum(math.dist(p, center) for p in inner) / n
                error = max(abs(radius - comp['outer_radii_m'][end]), abs(radius - inner_radius - comp['wall_m'][end]))
                max_section_error = max(max_section_error, error)
                if error > 0.00003:
                    failures.append(comp['id'])
        elif role == 'revolving_door_header':
            n = 64
            center = [sum(p[k] for p in vertices[:n]) / n for k in range(3)]
            diameter = 2 * sum(math.dist(p, center) for p in vertices[:n]) / n - 0.12
            doors.append({'id': comp['id'], 'centre_m': center, 'diameter_m': diameter})
        elif role == 'lobby_aluminium_panel':
            lobby_count += 1
            if abs(max(p[2] for p in vertices) - min(p[2] for p in vertices) - 7.0) > 0.00003:
                failures.append(comp['id'])
    lens = [p for item in recipe['objects'] if item['name'].startswith('ARC-APEX-LENS') for p in objects[item['name']].get('vertices_m', objects[item['name']].get('vertices'))]
    diameter = 2 * max((math.hypot(*p[:2]) for p in lens), default=0)
    height = max((p[2] for p in lens), default=0)
    barrier_triangles = []
    for item in recipe['objects']:
        if not item['name'].startswith('ARC-FACADE') and item['category'] not in ('INT_ENTRANCE', 'INT_DIAGRID'):
            continue
        native = objects[item['name']]
        vertices = native.get('vertices_m', native.get('vertices'))
        barrier_triangles.extend([vertices[i] for i in face] for face in native['triangles'] if min(vertices[i][2] for i in face) < 3 and max(vertices[i][1] for i in face) < -18)
    obstructions = []
    routes = recipe['entrance_routes']
    for route in routes:
        for offset in (-0.5, -0.25, 0, 0.25, 0.5):
            a, b = list(route['start_m']), list(route['end_m'])
            a[0] += offset
            b[0] += offset
            if any(segment_triangle(a, b, triangle) for triangle in barrier_triangles):
                obstructions.append({'door': route['door'], 'offset_m': offset})
    checks = [
        {'check': 'native_crown_CHS_and_lobby_sections', 'pass': not failures and crown_count > 0 and hollow_count == 684 and lobby_count == 28,
         'crown_members': crown_count, 'hollow_diagrid_members': hollow_count, 'lobby_panels': lobby_count,
         'maximum_section_error_m': max_section_error, 'failures': failures[:30],
         'scope': 'Gross triangular dimensions, CHS radius/wall at each end, 7 m panel height; no strength or fabrication check'},
        {'check': 'R06_native_apex_lens_diameter_and_height', 'pass': abs(diameter - 2.4) < 0.00003 and abs(height - 179.8) < 0.00003,
         'diameter_m': diameter, 'apex_z_m': height, 'scope': 'Published diameter; inferred lens curvature'},
        {'check': 'R11_four_native_revolving_door_proxies', 'pass': len(doors) == 4 and all(abs(d['diameter_m'] - settings['architecture']['entrance']['door_diameter_m']) < 0.00003 for d in doors),
         'doors': doors, 'scope': 'Count sourced; dimensions and coordinates inferred; operation not simulated'},
        {'check': 'entrance_approaches_have_real_facade_openings', 'pass': len(routes) == 4 and not obstructions,
         'sampled_routes': len(routes) * 5, 'obstructions': obstructions,
         'scope': 'Five horizontal torso-height rays across a 1 m approach strip against native facade and chevrons. Not an egress, accessibility or full-body collision certification'},
    ]
    upper = recipe['floors'][39]
    slab = next(c for c in recipe['components'] if c['level'] == 40 and c['role'] == 'perforated_slab')
    vertices, _ = component_mesh(slab, objects)
    p = settings['architecture']['upper_amenity']
    spans = [max(v[k] for v in vertices) - min(v[k] for v in vertices) for k in (0, 1)]
    expected = [p['mezzanine_centre_m'][0] + p['mezzanine_radius_m'] - p['mezzanine_flat_x_m'], 2 * p['mezzanine_radius_m']]
    treads = [c for c in recipe['components'] if c['role'] == 'curved_amenity_stair_tread']
    heights = [max(v[2] for v in component_mesh(c, objects)[0]) for c in treads]
    rise = (upper['ffl'] - recipe['floors'][38]['ffl']) / p['stair_risers']
    no_core = not any(c['level'] == 40 and c['role'] in ('stair_enclosure', 'lift_shaft', 'service_enclosure') for c in recipe['components'])
    checks.append({'check': 'R12_open_mezzanine_and_curved_stair',
                   'pass': no_core and len(treads) == p['stair_risers'] and len(upper.get('opening_polygons', [])) == 1
                           and max(abs(a - b) for a, b in zip(spans, expected)) < 0.00003
                           and all(abs(h - (recipe['floors'][38]['ffl'] + (j + 1) * rise)) < 0.00003 for j, h in enumerate(heights)),
                   'measured_spans_m': spans, 'treads': len(treads), 'inferred_rise_m': rise,
                   'scope': 'Native footprint and tread elevations; D-shaped topology observed, all metric setting-out inferred'})
    dining = [c for c in recipe['components'] if c['role'] == 'private_dining_table']
    if recipe.get('rooms'):
        checks.append({'check': 'R12_five_private_dining_room_proxies',
                       'pass': len([r for r in recipe['rooms'] if r['use'] == 'private_dining']) == 5 and len(dining) == 5,
                       'tables': len(dining), 'scope': 'Five rooms sourced; geometry and furniture are inferred proxies'})
    clashes, tested = [], 0
    cx, cy = p['stair_centre_m']
    for comp in recipe['components']:
        if comp['level'] not in (39, 40) or comp['role'] not in ('service_pipe', 'electrical_route'):
            continue
        vertices, _ = component_mesh(comp, objects)
        n = comp.get('endpoint_ring_size', settings['services']['pipe_radial_sides'])
        a, b = [[sum(v[k] for v in loop) / n for k in range(3)] for loop in (vertices[:n], vertices[n:2 * n])]
        if abs(a[2] - b[2]) > 0.00003:
            continue
        tested += 1
        count = max(1, math.ceil(math.dist(a, b) / 0.1))
        if any(math.hypot(a[0] + (b[0] - a[0]) * j / count - cx, a[1] + (b[1] - a[1]) * j / count - cy) < p['stair_opening_radius_m'] + comp['radius_m'] for j in range(count + 1)):
            clashes.append(comp['id'])
    checks.append({'check': 'upper_services_avoid_amenity_stair_zone', 'pass': not clashes, 'routes_checked': tested,
                   'failures': clashes[:30], 'scope': 'Horizontal native pipe/conduit samples at <=0.1 m outside the inferred circular stair zone'})
    return checks
